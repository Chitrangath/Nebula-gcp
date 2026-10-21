# GCP-003 Durable Object Storage Research

**Research and access date:** 2026-10-16

**Source policy:** official Cloudflare, AWS/Boto3, and Google Cloud
documentation only

**Scope:** design evidence for a provider-neutral S3-compatible storage
adapter; no account, bucket, credential, network-storage, or deployment action
was performed

## Decision summary

Nebula's Cloud Run API and owner-laptop worker can share durable objects through
one provider-neutral `StorageBackend` implemented against the S3 object API.
Keep `FileStorage` as the local/test adapter and add an S3-compatible adapter
whose endpoint, region, bucket, addressing behavior, and credentials are
injected configuration. Cloudflare R2 is a suitable deployment target because
Cloudflare documents S3 compatibility and demonstrates Boto3 use by changing
the endpoint URL and setting the SDK-required region to `auto`.
[Cloudflare: use R2 with S3 SDKs](https://developers.cloudflare.com/r2/get-started/s3/)

This is an application-level object seam, not a mounted-filesystem seam.
Cloud Run containers have a disposable, in-memory writable filesystem that
does not survive instance shutdown, so it cannot be the shared system of
record for the API and laptop worker.
[Google: disposable Cloud Run container filesystem](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run)

The adapter must support Nebula's accepted input, immutable model artifact,
result, and proof envelope as private objects, plus an authenticated backend
read path or a narrowly scoped, short-lived capability when a worker must
access an object directly. It must not expose bucket credentials or make the
bucket public.

## Provider-neutral client contract

The smallest useful S3-compatible client surface is:

- `PutObject` for bounded bytes with a server-derived key and content type;
- `GetObject` for bounded reads and backend-mediated authorized downloads;
- `HeadObject` for existence/size/metadata checks without downloading a body;
- `DeleteObject` for explicit cleanup and compensating cleanup after a later
  operation fails; and
- `generate_presigned_url` only when the protocol requires direct worker
  access to one object operation.

Boto3 exposes these as client methods and signs a presigned URL for a named
client operation, parameters, HTTP method, and expiry.
[Boto3: PutObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html),
[GetObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html),
[HeadObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/head_object.html),
[DeleteObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/delete_object.html),
[generate_presigned_url](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/generate_presigned_url.html)

The application interface should traffic in validated object keys and bytes,
not provider URLs or local paths. This keeps model/input/result/proof meanings
stable across `FileStorage`, the fake client used by tests, and an R2-backed
adapter. Provider exceptions should be translated into a small application
error vocabulary such as not found, already exists, invalid key, and storage
unavailable.

Configuration must fail closed. A remote adapter needs an explicit HTTPS
endpoint, bucket, region, access-key reference, secret-key reference, and
addressing choice; missing values, placeholders, endpoint user-info, insecure
HTTP, or a local adapter selection must reject the deployed GCP profile.
Cloudflare's documented R2 values are an account-specific HTTPS endpoint and
`region_name="auto"`; jurisdictional buckets require their corresponding
endpoint. Do not infer these values or commit the account identifier.
[Cloudflare: R2 authentication and jurisdictional endpoints](https://developers.cloudflare.com/r2/api/tokens/)

Addressing style should be an explicit compatibility option rather than being
embedded in Nebula's domain interface. The chosen owner configuration must be
tested against the real provider later; local fake-client tests establish
request construction and error handling, not endpoint/addressing interoperability.

## Private objects and least privilege

R2 buckets are not public by default, and public access requires a separate
explicit action. GCP-003 should rely on private S3 API access and must not
enable an `r2.dev` URL or custom public domain.
[Cloudflare: create private-by-default buckets](https://developers.cloudflare.com/r2/buckets/create-buckets/),
[public bucket behavior](https://developers.cloudflare.com/r2/buckets/public-buckets/)

The eventual owner-created parent token should use Object Read & Write and be
restricted to the one demonstration bucket. It should not receive account
administration or bucket-management permissions. Cloudflare documents
bucket-scoped object tokens and notes that object-level permissions are for
the S3-compatible API.
[Cloudflare: R2 API-token permissions](https://developers.cloudflare.com/r2/api/tokens/)

Long-lived access and secret keys belong only in the approved secret store and
trusted API/worker runtimes. They must never appear in Git, images, frontend
configuration, presigned-URL logs, evidence, exception text, or object
metadata. Because presigned URLs contain their authorization in the URL, they
are bearer capabilities and must also be omitted from logs and error messages.

For a single worker read or write, prefer a presigned URL limited to one
operation and one exact key with a short expiry. R2 supports presigned `GET`,
`HEAD`, `PUT`, and `DELETE` operations with expiry from one second through
seven days. The same URL can be reused until expiry, so the application should
choose the shortest practical TTL and treat leakage as valid access until
expiration.
[Cloudflare: R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)

If a caller genuinely needs several operations, R2 also supports temporary
credentials bound to one bucket and optionally to exact objects or prefixes.
They cannot exceed the parent token and should be constrained by actions and a
short TTL. The parent secret must never be shipped to the laptop worker or
browser merely to mint such credentials.
[Cloudflare: R2 temporary credentials](https://developers.cloudflare.com/r2/api/s3/temporary-credentials/)

No storage credential or capability belongs in the Vercel rewrite or browser
bundle. Browser users continue through authenticated `/api/v1/*` endpoints;
the backend authorizes the Nebula resource before reading an object or issuing
any capability.

## Keys, content, and trust boundaries

S3 object keys are not filesystem paths, but the same untrusted strings can
become paths under `FileStorage`. One shared validator should therefore apply
before every adapter operation:

- accept only non-empty, normalized relative keys within a conservative byte
  limit smaller than the provider's maximum;
- reject absolute paths, backslashes, empty segments, `.` and `..` segments,
  control characters, URL/query fragments, repeated separators, and values
  that change after normalization;
- require a server-owned namespace and server-derived identifiers for each
  object class, for example distinct input, model, result, and proof prefixes;
  and
- never accept a client-supplied local path, bucket name, endpoint, or complete
  object URL as authority.

R2's current maximum object-key length is 1,024 bytes, but that provider limit
is not itself an application security policy.
[Cloudflare: R2 limits](https://developers.cloudflare.com/r2/platform/limits/)

The API should compute and persist hashes from the bytes it actually accepts.
On worker result/proof ingestion, independently read or stream the stored bytes
under configured size limits and recompute the protocol hash; never trust a
client-supplied hash, ETag, key, content length, or metadata field. An S3 ETag
is an object-store concurrency identifier, not Nebula's protocol digest.

## Atomicity, overwrite prevention, and cleanup

For single-part `PutObject`, Amazon documents that a success means the entire
object was added and no partial object is created. Create-once semantics require
an atomic conditional put using `If-None-Match: *`; an ordinary read-then-write
existence check races. S3 returns `412 Precondition Failed` when the key exists
and can return `409 Conflict` during a conflicting operation.
[AWS: Boto3 PutObject semantics](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html),
[AWS: conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)

R2 specifically documents that `PutObject` conditional headers are evaluated
atomically with the committed bucket state; concurrent create-if-absent writes
permit at most one success. The adapter can therefore expose an explicit
create-only operation, but tests must verify the exact `IfNoneMatch="*"`
request and translate `412`/relevant `409` responses. Do not silently fall
back to check-then-put for an S3-compatible provider that lacks conditional
put support.
[Cloudflare: R2 S3 API compatibility](https://developers.cloudflare.com/r2/api/s3/api/)

R2 provides strong read-after-write, delete, metadata-update, and listing
consistency. Without a conditional header, simultaneous writes to one key use
last-writer-completes behavior, which is unsuitable for immutable Nebula
artifacts.
[Cloudflare: R2 consistency model](https://developers.cloudflare.com/r2/reference/consistency/)

Object storage and PostgreSQL do not form one transaction. Safe sequencing
must minimize orphaned objects and perform a best-effort compensating delete
when an object write succeeds but the authoritative database transition fails.
Cleanup failure must be surfaced for monitoring/retry without hiding the
original error. Conversely, do not delete an existing immutable object after
a create-only conflict. A later owner-authorized environment should exercise
failure injection and orphan reconciliation against the real provider.

`DeleteObject` is not proof that the caller supplied the right key. Delete only
validated, server-derived keys after authorization. Where deletion is part of
a multi-step failure path, tests should cover both successful cleanup and a
cleanup failure that leaves an explicit recoverable error/evidence trail.

## Test boundary for GCP-003

A fake S3 client can prove locally that the adapter:

- maps put/get/head/delete and presign operations to the configured bucket and
  validated key;
- always requests create-only conditional writes for immutable objects;
- rejects traversal and malformed keys before calling the client;
- does not request public ACLs or emit credentials/capability URLs;
- bounds content and capability TTLs;
- closes response bodies and translates not-found/conflict/provider failures;
- attempts compensating cleanup when a later local step fails; and
- allows independently configured API and laptop-worker adapter instances to
  observe the same fake backing store through the shared interface.

That evidence does **not** prove an R2 bucket exists, a token is correctly
scoped, the configured endpoint/addressing mode works, real conditional writes
behave as expected, cross-runtime access succeeds, latency/egress is acceptable,
or cleanup works under provider failure. Those remain later, explicit
owner-authorized acceptance gates using non-production objects and no public
bucket access.

## GCP-003 implementation recommendation

Implement one domain-level storage interface with `FileStorage` and
S3-compatible adapters behind configuration. Keep keys and hashes owned by
Nebula, keep objects private, use conditional create for immutable writes, and
prefer backend-mediated reads. If direct laptop-worker access is necessary,
issue a short-lived presigned capability for one exact operation and key.

The Cloud Run template and validator should require the remote adapter plus
non-placeholder endpoint, region, bucket, and secret references, while still
forbidding runners. The laptop worker must use the same bucket/namespace under
a separately provisioned least-privilege credential. No claim of deployability
or remote-storage integration is justified until a later owner-authorized
bucket/IAM test proves cross-runtime put/read/delete behavior.
