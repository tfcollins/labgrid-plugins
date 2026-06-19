# Releasing the hw-request family

Consumers pin `uses: tfcollins/labgrid-plugins/.github/workflows/<wf>.yml@v<N>`.
A tag is only frozen if the workflows' *internal* self-references are pinned
too — that's what `scripts/pin-release-refs.sh` does.

1. `git checkout -b release/v<N> main`
2. `scripts/pin-release-refs.sh v<N>`
2b. `nox -s release_guard` — verify no `@main` self-refs remain (do NOT run on main).
3. `git commit -am "release: pin internal refs to v<N>"`
4. `git push -u origin release/v<N>`
5. `git tag v<N> && git push origin v<N>`
6. `gh release create v<N> --generate-notes`
7. Open a PR to main updating the pinning guidance (AGENTS.md, onboarding
   templates) to the new tag.

Release branches are cut and tagged, **never merged back** — main keeps
`@main` internals so development stays self-testing.
