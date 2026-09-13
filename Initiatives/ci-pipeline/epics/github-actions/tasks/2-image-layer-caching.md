## Docker layer caching so CI doesn't rebuild the image cold every run

- **Depends on:** task 1 (a working workflow to cache).
- **Why:** `Dockerfile` installs an Android SDK (cmdline-tools, platform 34,
  build-tools, emulator system image) and builds Eclipse Cyclone DDS +
  ddscxx from source — both genuinely slow. A cold rebuild on every push
  makes the gate too slow to be useful; the fix is caching, not trimming the
  image (nothing in it is unused — see the Dockerfile's own per-layer
  comments for what each piece backs).
- **Deliverable:** wire a GitHub Actions cache (e.g.
  `docker/build-push-action` with `cache-from`/`cache-to: type=gha`, or
  `docker/setup-buildx-action` + the `actions/cache` backend — pick whichever
  needs less custom scripting) keyed on a hash of `Dockerfile` +
  `.dockerignore`, mirroring `Docker/_env.sh`'s existing
  `HARPIA_IMAGE=harpia-build:<sha256 of those same two files>` scheme so a
  cache hit/miss tracks the same "did the toolchain actually change"
  question local clones already answer that way.
- **Out of scope:** caching pytest's own state (no such cache exists locally
  either — a cold `Docker/run.sh pytest UnitTests/` run is the baseline to
  match, not to beat), caching the Gradle dependency cache (a separate,
  optional follow-up — `HARPIA_GRADLE_VOLUME` is a Docker volume, not a
  layer, and doesn't exist on a fresh CI runner by default).
- **Verification:** two consecutive pushes with no `Dockerfile`/
  `.dockerignore` change — second run's image-build step should be
  visibly faster (cache hit), not a full rebuild. A push that *does* touch
  `Dockerfile` should still produce a correct (if slower, cache-miss) run —
  confirm this too, so a real toolchain change is never silently served a
  stale cached image.
