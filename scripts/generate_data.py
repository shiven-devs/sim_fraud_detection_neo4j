"""
Build a synthetic Mini-ASTR dataset.

Photos come from the public Labeled Faces in the Wild benchmark via scikit-learn.
KYC fields come from Faker (en_IN) and are not real subscriber records.

Planted fraud uses different photos of the same LFW person, never the same file:
  (a) 6 people, each registered 2 or 3 times under slightly altered names
  (b) one subscriber with 10 SIMs
  (c) one face shared by two differently named subscribers with one bank account
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from faker import Faker
from PIL import Image
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
FACES_DIR = ROOT / "faces"
DATA_DIR = ROOT / "data"
TSPS = ["Jio", "Airtel", "Vi"]
# 6 people, 15 subscriber records. Within the requested 5-8 people, 2-3 records each.
FRAUD_ALIAS_COUNTS = [3, 2, 3, 2, 3, 2]


def safe_dir(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)
    return cleaned.strip("_") or "person"


def save_face(pixels: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(pixels)
    if arr.dtype != np.uint8:
        # sklearn returns floats in 0..1
        arr = np.clip(arr, 0, 1)
        arr = (arr * 255).astype(np.uint8)
    if arr.ndim == 2:
        image = Image.fromarray(arr, mode="L").convert("RGB")
    else:
        image = Image.fromarray(arr[..., :3], mode="RGB")
    image.save(path, quality=95)


def random_date(rng: random.Random, start: int, end: int) -> str:
    return f"{rng.randint(start, end):04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def tweak_name(name: str, rng: random.Random) -> str:
    """One-character edit or adjacent swap. Kept only if it still fuzzy-matches the base name."""
    chars = list(name)
    letters = [i for i, c in enumerate(chars) if c.isalpha()]
    if len(letters) < 4:
        return name + "h"
    if rng.random() < 0.4:
        i = rng.choice(letters[:-1])
        later = [j for j in letters if j > i]
        j = later[0]
        chars[i], chars[j] = chars[j], chars[i]
        return "".join(chars)
    choices = [i for i in letters if i > 0 and chars[i - 1] != " "]
    i = rng.choice(choices or letters[1:])
    del chars[i]
    return "".join(chars)


def name_variants(base: str, count: int, rng: random.Random, used: set[str]) -> list[str]:
    names = [base]
    attempts = 0
    while len(names) < count and attempts < 40:
        attempts += 1
        candidate = tweak_name(base, rng)
        if candidate in names or candidate in used or candidate.strip() == "":
            continue
        # Planted aliases should trip the >85 fuzzy rule against the original name.
        if fuzz.token_sort_ratio(base, candidate) <= 85:
            continue
        names.append(candidate)
        used.add(candidate)
    if len(names) < count:
        raise RuntimeError(f"Could not build {count} fuzzy name variants for {base!r}")
    return names


def unique_name(fake: Faker, rng: random.Random, used: set[str], dissimilar_to: str | None = None) -> str:
    for _ in range(50):
        candidate = fake.name()
        if candidate in used:
            continue
        if dissimilar_to and fuzz.token_sort_ratio(candidate, dissimilar_to) > 70:
            continue
        used.add(candidate)
        return candidate
    fallback = f"{fake.first_name()} {fake.last_name()} {rng.randint(10, 99)}"
    used.add(fallback)
    return fallback


def make_sims(rng: random.Random, count: int, used_numbers: set[str]) -> list[dict]:
    sims = []
    for _ in range(count):
        while True:
            number = rng.choice("6789") + "".join(rng.choice("0123456789") for _ in range(9))
            if number not in used_numbers:
                used_numbers.add(number)
                break
        sims.append(
            {
                "number": number,
                "activated_on": random_date(rng, 2018, 2025),
                "tsp": TSPS[len(used_numbers) % len(TSPS)],
            }
        )
    return sims


def new_subscriber(
    *,
    serial: int,
    name: str,
    rng: random.Random,
    fake: Faker,
    used_kyc: set[str],
    used_banks: set[str],
    used_numbers: set[str],
    image_path: str,
    sim_count: int,
    bank_account: str | None = None,
    dob: str | None = None,
) -> dict:
    while True:
        kyc_id = "SYN" + "".join(rng.choice("0123456789") for _ in range(12))
        if kyc_id not in used_kyc:
            used_kyc.add(kyc_id)
            break
    if bank_account is None:
        while True:
            bank_account = f"DEMO{rng.randint(0, 9999999):07d}-{rng.randint(0, 999999999999):012d}"
            if bank_account not in used_banks:
                used_banks.add(bank_account)
                break
    sub_id = f"SUB-{serial:04d}"
    return {
        "id": sub_id,
        "name": name,
        "dob": dob or random_date(rng, 1965, 2002),
        "address": fake.address().replace("\n", ", "),
        "kyc_id": kyc_id,
        "bank_account": bank_account,
        "face_id": f"FACE-{sub_id}",
        "image_path": image_path,
        "sims": make_sims(rng, sim_count, used_numbers),
    }


def group_people(lfw) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, label in enumerate(lfw.target):
        buckets[str(lfw.target_names[label])].append(int(index))
    return buckets


def take_person(pool: list[str], buckets: dict[str, list[int]], needed: int) -> str:
    while pool:
        name = pool.pop(0)
        if len(buckets[name]) >= needed:
            return name
    raise RuntimeError(
        f"LFW subset does not contain enough people with at least {needed} photos. "
        "Re-run after the LFW download finishes, or lower the subscriber count."
    )


def build(subscriber_count: int = 100) -> None:
    alias_total = sum(FRAUD_ALIAS_COUNTS)
    shared_total = 2
    excess_total = 1
    overhead = alias_total + shared_total + excess_total
    if subscriber_count < overhead + 10:
        raise SystemExit(f"--subscribers must be at least {overhead + 10}")

    rng = random.Random(42)
    fake = Faker("en_IN")
    fake.seed_instance(42)
    np.random.seed(42)

    print("Downloading LFW via sklearn (first run can take several minutes)...")
    from sklearn.datasets import fetch_lfw_people

    # min_faces_per_person=3 gives every kept person enough distinct photos for planted duplicates.
    lfw = fetch_lfw_people(min_faces_per_person=3, color=True, resize=0.5)
    buckets = group_people(lfw)
    pool = sorted(buckets)
    print(f"LFW people with 3+ photos: {len(pool)}")

    normal_count = subscriber_count - overhead
    needed_people = len(FRAUD_ALIAS_COUNTS) + 2 + normal_count
    if len(pool) < needed_people:
        normal_count = len(pool) - len(FRAUD_ALIAS_COUNTS) - 2
        print(f"Warning: only {len(pool)} people available. Generating {normal_count} ordinary subscribers.")
        if normal_count < 1:
            raise SystemExit("Not enough LFW people to plant fraud and keep one ordinary subscriber.")

    used_names: set[str] = set()
    used_kyc: set[str] = set()
    used_banks: set[str] = set()
    used_numbers: set[str] = set()
    subscribers: list[dict] = []
    same_face_clusters: list[dict] = []
    serial = 1

    def assign_photo(person: str, photo_index: int) -> str:
        image_index = buckets[person][photo_index]
        relative = f"faces/{safe_dir(person)}/{photo_index}.jpg"
        save_face(lfw.images[image_index], ROOT / relative)
        return relative

    for cluster_number, alias_count in enumerate(FRAUD_ALIAS_COUNTS, start=1):
        person = take_person(pool, buckets, alias_count)
        base_name = unique_name(fake, rng, used_names)
        aliases = name_variants(base_name, alias_count, rng, used_names)
        member_ids = []
        for offset, alias in enumerate(aliases):
            subscriber = new_subscriber(
                serial=serial,
                name=alias,
                rng=rng,
                fake=fake,
                used_kyc=used_kyc,
                used_banks=used_banks,
                used_numbers=used_numbers,
                image_path=assign_photo(person, offset),
                sim_count=rng.randint(1, 2),
                dob=random_date(rng, 1968, 1998),
            )
            serial += 1
            subscribers.append(subscriber)
            member_ids.append(subscriber["id"])
        same_face_clusters.append(
            {
                "id": f"GT-FACE-{cluster_number}",
                "kind": "altered_names",
                "benchmark_person": person,
                "subscriber_ids": member_ids,
                "names": aliases,
                "note": "Different photos of one LFW person, fuzzy name edits, different dates of birth and SIMs.",
            }
        )

    shared_person = take_person(pool, buckets, 2)
    shared_bank = f"DEMO{rng.randint(0, 9999999):07d}-{rng.randint(0, 999999999999):012d}"
    used_banks.add(shared_bank)
    shared_ids = []
    shared_names = []
    first_shared = unique_name(fake, rng, used_names)
    second_shared = unique_name(fake, rng, used_names, dissimilar_to=first_shared)
    for offset, name in enumerate((first_shared, second_shared)):
        subscriber = new_subscriber(
            serial=serial,
            name=name,
            rng=rng,
            fake=fake,
            used_kyc=used_kyc,
            used_banks=used_banks,
            used_numbers=used_numbers,
            image_path=assign_photo(shared_person, offset),
            sim_count=rng.randint(1, 2),
            bank_account=shared_bank,
            dob=random_date(rng, 1972, 1999),
        )
        serial += 1
        subscribers.append(subscriber)
        shared_ids.append(subscriber["id"])
        shared_names.append(name)
    same_face_clusters.append(
        {
            "id": "GT-FACE-SHARED-BANK",
            "kind": "shared_bank",
            "benchmark_person": shared_person,
            "subscriber_ids": shared_ids,
            "names": shared_names,
            "note": "Same face, dissimilar names, one shared synthetic bank account.",
        }
    )
    shared_bank_cases = [
        {
            "id": "GT-BANK-1",
            "bank_account": shared_bank,
            "subscriber_ids": shared_ids,
            "names": shared_names,
        }
    ]

    excess_person = take_person(pool, buckets, 1)
    excess_name = unique_name(fake, rng, used_names)
    excess = new_subscriber(
        serial=serial,
        name=excess_name,
        rng=rng,
        fake=fake,
        used_kyc=used_kyc,
        used_banks=used_banks,
        used_numbers=used_numbers,
        image_path=assign_photo(excess_person, 0),
        sim_count=10,
    )
    serial += 1
    subscribers.append(excess)

    for _ in range(normal_count):
        person = take_person(pool, buckets, 1)
        subscriber = new_subscriber(
            serial=serial,
            name=unique_name(fake, rng, used_names),
            rng=rng,
            fake=fake,
            used_kyc=used_kyc,
            used_banks=used_banks,
            used_numbers=used_numbers,
            image_path=assign_photo(person, 0),
            sim_count=rng.randint(1, 3),
        )
        serial += 1
        subscribers.append(subscriber)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dataset = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "sklearn.datasets.fetch_lfw_people + Faker en_IN",
        "warning": "Synthetic KYC and public benchmark photos only. Not subscriber data.",
        "tsps": TSPS,
        "subscribers": subscribers,
    }
    ground_truth = {
        "description": "Planted cases for precision and recall. Detection must not read this file except in GET /evaluate.",
        "same_face_clusters": same_face_clusters,
        "excess_sims": [{"subscriber_id": excess["id"], "sim_count": 10, "name": excess["name"]}],
        "shared_bank": shared_bank_cases,
    }
    (DATA_DIR / "subscribers.json").write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    (DATA_DIR / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

    sim_count = sum(len(person["sims"]) for person in subscribers)
    print(f"Subscribers: {len(subscribers)}")
    print(f"SIMs: {sim_count}")
    print(f"Planted same-face clusters: {len(same_face_clusters)}")
    print(f"Excess-SIM subscriber: {excess['id']} ({excess['name']}) with 10 SIMs")
    print(f"Shared bank account: {shared_bank} ({', '.join(shared_names)})")
    print(f"Wrote {DATA_DIR / 'subscribers.json'}")
    print(f"Wrote {DATA_DIR / 'ground_truth.json'}")
    print(f"Wrote photos under {FACES_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic Mini-ASTR subscribers and LFW face files")
    parser.add_argument("--subscribers", type=int, default=100, help="Total subscriber records, including planted cases")
    args = parser.parse_args()
    build(args.subscribers)


if __name__ == "__main__":
    main()
