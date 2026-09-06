# Security and trust boundaries

## Reporting

Use GitHub private vulnerability reporting when available. While the repo is private, contact the maintainer through an existing private channel. Do not put credentials or exploitable production details in an issue or test another person's services.

## Scope

This library is not a sandbox. Python model/tool callbacks execute with the embedding application's permissions. Native tools remain subject to their host's permissions. Valid JSON is not business authorization.

- Owner IDs coordinate cooperating clients; they do not authenticate tenants.
- The MCP server is STDIO-only. Do not expose it through an unauthenticated network bridge.
- Scanner paths are confined to the selected project; symlinks/junctions, known secret filenames and ignored files are excluded/rejected. Redaction is best effort. Inspect prepared inventories before sending sensitive projects to a remote generator.
- Python scanning uses AST, not imports or execution.
- JSON inputs are bounded. Duplicate keys, non-finite values and unsupported objects are rejected. Schema references and unrestricted regex patterns are disabled.
- State/artifacts can contain sensitive data. Keep `.skillstate/local/` out of version control and use OS permissions and an appropriate retention policy.
- Generated MCP configuration contains local paths; keep it local and respect host trust policies.

## External effects

`pending` and `unknown` operations require inspection of the external system before reconciliation. They are not permission to repeat a deployment, payment, mutation or message.

Timeouts cancel waiting, not necessarily the external operation. A synchronous handler running in a thread can continue after timeout. Prefer cancellable asynchronous clients and service-level idempotency for production integrations.

Supply application-level authorization, argument constraints, result validation, completion checks and recovery procedures. A local transaction cannot guarantee exactly-once effects across arbitrary remote systems.
