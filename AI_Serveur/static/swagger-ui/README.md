Swagger UI 5.35.0 (`swagger-ui-dist`, Apache-2.0), copied unchanged from the npm package so
that the documentation page loads nothing from another host: `swagger-ui-bundle.js`,
`swagger-ui.css`, `LICENSE` and `NOTICE`, and `favicon-32x32.png` as `favicon.png`.
`init.js` is ours.

To update: `npm pack swagger-ui-dist@<version>`, check the tarball against the integrity hash
`npm view swagger-ui-dist@<version> dist.integrity` prints, copy the same files, and run the
tests.
