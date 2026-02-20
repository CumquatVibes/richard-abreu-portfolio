#!/usr/bin/env python3
"""Reorganize channel_tokens.json so each token maps to its ACTUAL channel.

The initial OAuth flow captured tokens with mismatched labels (user clicked through
brand accounts in random order). This script remaps each token to the channel it
actually authenticates as, deduplicates, and identifies which channels still need tokens.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TOKENS_PATH = os.path.join(BASE_DIR, "channel_tokens.json")

# All 38 faceless channels: name -> expected channel_id
ALL_CHANNELS = {
    "Cumquat Motivation": "UCtrCefKinhom7LFBV8rnfpQ",
    "RichTech": "UCH7Om9fi1IA3SrRXmx2vApQ",
    "RichAnimation": "UCtsmXjQaCdMTEyDTDWRpVVA",
    "RichFashion": "UCf0Y1kCz_2nTmKpJtPQKoyg",
    "RichFamily": "UC3rXZPP828z8w9UdEdQEWtw",
    "RichBeauty": "UCfBoNA8eUrqmSTPLtMhrpdQ",
    "RichCooking": "UC8OrR3UMdyzy4DRgmCWOXcA",
    "RichEducation": "UCp3WkXsFFzdRLZX_UYp43cw",
    "RichHistory": "UC1pCR2B_mQwCacIlvRhUacA",
    "RichNature": "UCqzGBwIvr3sY1nUc9M2EVsg",
    "RichCrypto": "UCc5XhfHIkEp5WwG9CRZm_6w",
    "RichScience": "UC0ODvK8Hvrd9Bd3QWIWPecA",
    "RichTravel": "UCEA1FMT0W2lS93Ig1W1ddUA",
    "RichVlogging": "UCfcF72fTPY1khgl5bEHzZEQ",
    "RichGaming": "UCxa7nahEFd_39_jUl-VB57A",
    "RichReviews": "UCQZAmWq2Y_1W09mIOSRSrFw",
    "RichKids": "UCTR_qaU4bdip3DSvgBkRMGA",
    "RichPets": "UCqPWKbwAGtKfiay4fB8bF1g",
    "RichHorror": "UCoWN7G6XuFBPgM-m3d1ZMvQ",
    "RichMovie": "UCuQwKYGe1hNdbQqJH51qqAw",
    "Rich Business": "UCPQ8N53EgcqEKR4SfQ1DcXQ",
    "RichFitness": "UCYelLGcByI-Qh94two6CaMA",
    "RichMusic": "UCCI_ynXNuutXGrzWDYzUZiA",
    "RichFinance": "UCJwfAudM4c4rWSk3P8iib8g",
    "RichCars": "UCr0q31TN0vW0c65JUD0eaBw",
    "RichLifestyle": "UC1Qnne6cR4N4RJgpySYUevw",
    "RichPhotography": "UCZLGO4ioG50Y3FBK3oLKmpA",
    "RichSports": "UCE33LOzIvklXaPbH1920vqQ",
    "RichFood": "UCSRXBfCZTafYTtfH9KF-SZw",
    "RichMemes": "UC5Sa2tKSk-5Nek01b-v1LpQ",
    "RichDesign": "UCSc0w6tez-UI3fyXQbUcF5g",
    "RichComedy": "UC7OZtJLgHJ1ooWWlPLRYIXg",
    "RichDIY": "UC7dfL3CGJCbG7QcGnjrmqbQ",
    "RichDance": "UCsNqeu5ZPnBOE3liu9-ofYg",
    "Eva Reyes": "UCsp5NIA6aeQmqdn7omBqkYg",
    "RichMind": "UCvrGunMx9dVfAeGYLQYoaLw",
    "How to Meditate": "UCbd6kzX3giNYyAeLaMPdgAA",
    "How to Use AI": "UCkrCbfr9qQkfCYw1WkCILKQ",
}

# Reverse lookup: channel_id -> proper name
ID_TO_NAME = {v: k for k, v in ALL_CHANNELS.items()}


def main():
    with open(CHANNEL_TOKENS_PATH) as f:
        raw_tokens = json.load(f)

    print(f"Raw tokens loaded: {len(raw_tokens)} entries\n")

    # Build map from actual channel_id -> token data (dedup, keep first)
    id_to_token = {}
    for label, data in raw_tokens.items():
        cid = data["channel_id"]
        if cid not in id_to_token:
            id_to_token[cid] = data

    print(f"Unique channel tokens: {len(id_to_token)}\n")

    # Remap to correct channel names
    clean_tokens = {}
    extra_tokens = {}

    for cid, data in id_to_token.items():
        proper_name = ID_TO_NAME.get(cid)
        if proper_name:
            clean_tokens[proper_name] = data
        else:
            # Channel not in our 38 list (main account, Cumquat Vibes, etc.)
            extra_tokens[data["channel_title"]] = data

    # Save cleaned tokens
    with open(CHANNEL_TOKENS_PATH, "w") as f:
        json.dump(clean_tokens, f, indent=2)

    # Report
    print(f"AUTHORIZED ({len(clean_tokens)}/38 channels):")
    for name in sorted(clean_tokens.keys()):
        cid = clean_tokens[name]["channel_id"]
        title = clean_tokens[name]["channel_title"]
        print(f"  {name} ({title}) - {cid}")

    if extra_tokens:
        print(f"\nEXTRA (not in our 38, discarded from tokens file):")
        for name, data in extra_tokens.items():
            print(f"  {name} ({data['channel_id']})")

    # Find missing
    missing = []
    for name, expected_id in ALL_CHANNELS.items():
        if name not in clean_tokens:
            missing.append((name, expected_id))

    if missing:
        print(f"\nSTILL NEED TOKENS ({len(missing)} channels):")
        for name, cid in missing:
            print(f"  {name} ({cid})")
    else:
        print("\nAll 38 channels authorized!")


if __name__ == "__main__":
    main()
