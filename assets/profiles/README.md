# `assets/profiles/`

This directory stores client profile assets from different therapeutic schools, reused by `src/sample` and `src/rft` through dataset configurations.

The directory structure follows the `DatasetLoader` convention:

```text
profiles/
  bt/sample/*.json
  bt/rft/*.json
  cbt/sample/*.json
  cbt/rft/*.json
  ...
```

Notes:

- `sample/`: the profile split used by `src/sample`.
- `rft/`: the profile split used by `src/rft`.
- Currently only the `sample` and `rft` splits are organized; the historical `dev` / `rl` splits were not merged into the official `v0402` asset directory.

Recommended companion configurations:

- [`../../configs/datasets/profiles_sample.yaml`](../../configs/datasets/profiles_sample.yaml)
- [`../../configs/datasets/profiles_rft.yaml`](../../configs/datasets/profiles_rft.yaml)
