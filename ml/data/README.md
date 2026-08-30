# Dataset Setup

This folder contains the datasets used for the Financial Crime Detection project.

## Required Dataset

The main transaction dataset is:

`HI-Small_Trans.csv`

⚠️ **This file is NOT stored in GitHub** because it is approximately **454 MB**.

### Setup

1. Obtain `HI-Small_Trans.csv`.
2. Place it inside this folder:

```text
ml/data/HI-Small_Trans.csv
```

3. Verify the file:

```bash
ls -lh ml/data/HI-Small_Trans.csv
```

The file should be approximately **454 MB**.

## Files in this folder

```text
ml/data/
├── HI-Small_Trans.csv       # Large transaction dataset (local only)
├── HI-Small_accounts.csv    # Account data
├── HI-Small_Patterns.txt    # Pattern information
└── README.md                # Dataset instructions
```

The transaction CSV is intentionally ignored by Git and should **not** be committed or force-added to the repository.
