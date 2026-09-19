# Patched flet-dropzone for Flet 1.0

Upstream [flet-dropzone](https://github.com/shiena/flet-dropzone) 0.4.0 pins
Flutter dependency `flet: ^0.80.0`, which excludes Flet 1.x under pub
versioning.

This vendor copy only changes that constraint to `flet: ">=0.80.0"` so
`flet build` can resolve against Flet 1.0 while keeping the same Dropzone API.

Wired via `[tool.uv.sources]` and `[tool.flet.dev_packages]` in the repo
`pyproject.toml`.
