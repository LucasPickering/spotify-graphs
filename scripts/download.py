#!/usr/bin/env python3

import argparse
import itertools
import json
from typing import Any

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--creds", default="creds.json")
    parser.add_argument("--output", "-o", default="data/tracks.json")
    args = parser.parse_args()

    with open(args.creds) as f:
        creds = json.load(f)

    # Exchange creds for a temporary access token
    access_token = get_access_token(creds)

    with httpx.Client(
        base_url="https://api.spotify.com",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as client:
        tracks = search(client, "test")
        # Grab all the artist IDs so we can do a separate request to get genres
        artist_ids = set(
            artist["id"] for track in tracks for artist in track["artists"]
        )
        genres = get_genres(client, list(artist_ids))

    # Join tracks with their genres
    for track in tracks:
        track["genres"] = list(
            {genre for artist in track["artists"] for genre in genres[artist["id"]]}
        )

    with open(args.output, "w") as f:
        json.dump(tracks, f, indent=4)


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


def search(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    response = client.get(
        "/v1/search", params={"type": "track", "q": query, "limit": 50}
    )
    response.raise_for_status()
    return response.json()["tracks"]["items"]


def get_genres(client: httpx.Client, artists: list[str]) -> dict[str, list[str]]:
    mapping = {}
    for chunk in chunked(artists, 50):
        response = client.get("/v1/artists", params={"ids": ",".join(chunk)})
        response.raise_for_status()
        for artist in response.json()["artists"]:
            mapping[artist["id"]] = artist["genres"]
    return mapping


def chunked(l, n):
    for i in range(0, len(l), n):
        yield l[i : i + n]


if __name__ == "__main__":
    main()
