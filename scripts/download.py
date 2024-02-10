#!/usr/bin/env python3

import argparse
import asyncio
import itertools
import json
from typing import Any

import httpx
from tqdm.asyncio import tqdm

MAX_SEARCH_SIZE = 50
MAX_ARTIST_SIZE = 50
TRACK_KEYS = {"id", "genres", "duration_ms", "name"}


def main() -> None:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--creds", default="creds.json")
    parser.add_argument("--output", "-o", default="data/tracks.json")
    parser.add_argument("--search-terms", default="search_terms.txt")
    args = parser.parse_args()

    with open(args.creds) as f:
        creds = json.load(f)

    with open(args.search_terms) as f:
        search_terms = f.readlines()

    # Exchange creds for a temporary access token
    access_token = get_access_token(creds)
    tracks = asyncio.run(download_tracks(access_token, search_terms))

    with open(args.output, "w") as f:
        json.dump(tracks, f)


async def download_tracks(
    access_token: str, search_terms: list[str]
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(
        base_url="https://api.spotify.com",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as client:
        # First, run each search term and take the first page of results
        print("Downloading tracks")
        tracks = {
            track["id"]: track
            for tracks in await tqdm.gather(
                *(search(client, query) for query in search_terms),
                total=len(search_terms),
            )
            for track in tracks
        }

        # Grab all the artist IDs so we can do a separate request to get genres
        artist_ids = {
            artist["id"] for track in tracks.values() for artist in track["artists"]
        }

        print("Downloading artists")
        artists = itertools.chain.from_iterable(
            await tqdm.gather(
                *(
                    download_artists(client, ids)
                    for ids in chunked(artist_ids, MAX_ARTIST_SIZE)
                )
            )
        )

    # Map each artist to their genres
    artist_genres = {artist["id"]: artist["genres"] for artist in artists}

    # Join tracks with their genres
    for track in tracks.values():
        keys_to_delete = set(track.keys()) - TRACK_KEYS
        track["genres"] = list(
            {
                genre
                for artist in track["artists"]
                for genre in artist_genres[artist["id"]]
            }
        )
        for key in keys_to_delete:
            del track[key]

    return list(tracks.values())


def get_access_token(creds):
    response = httpx.post(
        "https://accounts.spotify.com/api/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def search(client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
    response = await client.get(
        "/v1/search", params={"type": "track", "q": query, "limit": MAX_SEARCH_SIZE}
    )
    response.raise_for_status()
    return response.json()["tracks"]["items"]


async def download_artists(
    client: httpx.AsyncClient, ids: list[str]
) -> dict[str, list[str]]:
    response = await client.get("/v1/artists", params={"ids": ",".join(ids)})
    response.raise_for_status()
    return response.json()["artists"]


def chunked(iterable, n):
    it = iter(iterable)
    while batch := tuple(itertools.islice(it, n)):
        yield batch


if __name__ == "__main__":
    main()
