"""Packaging the data a deployed API needs, without committing it to Git.

The API reads Parquet directly off disk at request time (Bronze + Silver, joined on `id`).
That data is deliberately never in Git and never in a build artifact. To reach Render it is
packaged here into a portable `tar.gz` whose directory entries are stored `0755` and file
entries `0644`, so GNU tar on the far side can extract and then write into every directory.
The prior archive stored directories `0555`, which made them read-only and broke extraction.
"""
