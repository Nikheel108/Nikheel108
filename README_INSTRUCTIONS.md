Quick instructions to run the generated profile visual locally or in Codespaces.

1) Requirements

 - Python 3.8+
 - `requests` (install via `pip install -r requirements.txt`)

2) Running in a Codespace or local machine

 - Set your token and run the script:

```bash
export GITHUB_TOKEN="your_personal_token_with_repo_scope"
python3 scripts/generate_profile_visual.py
```

This will upload `assets/activity.svg` and update the `README.md` in your profile repository (the repo named after your username). If the profile repo isn't found among your owned repos, the script will write a local `assets_activity.svg` instead.

3) Running in GitHub Actions

 - The workflow `.github/workflows/generate_profile_visual.yml` runs weekly and on manual dispatch. It expects a repository secret named `PERSONAL_TOKEN` containing a Personal Access Token with `repo` (or repository `Contents: Read & write`) permissions. Create that secret under: Settings → Secrets and variables → Actions → New repository secret, and name it `PERSONAL_TOKEN`.
