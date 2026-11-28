# In-chat progress with ReUI and Vercel AI SDK UI

Use this recipe **only when you control the React chat frontend and its streaming endpoint**. Vercel AI SDK UI transports typed events; ReUI renders them. Neither adds a renderer to an existing Codex or other third-party conversation. For a host you do not control, use its native in-chat progress channel unless it exposes a verified extension that can receive and update the same surface; otherwise use the final-reply fallback in [Agent Progress](SKILL.md). A separate browser is not a fallback for in-chat work.

## Stream one card per run

1. **Define the data contract.** Use a `run-progress` entry in the `UIMessage` data types. Send a full display snapshot: `runId`, a monotonic revision if the source supports replay, a short activity label, the run state, optional `{completed, total, unit}`, and an optional user-safe blocker, next action, or verification summary. Read the worker, journal, or tool result; do not have the model guess a state. Validate incoming data at the boundary. Scope the subscription to an authorized run and send only evidence safe for the conversation and its retention policy.
2. **Write the data part.** In `createUIMessageStream`, start the assistant message once and call `writer.write({ type: 'data-run-progress', id: runId, data: snapshot })` at meaningful milestones, including the verified terminal outcome. Return the stream with `createUIMessageStreamResponse`. Reuse the same part ID **within the same assistant message** so updates replace the existing part rather than adding rows. Keep this part non-transient so it renders in `message.parts`; use a transient part and `onData` only for ephemeral feedback. Rendering in message history is not durable storage: persist the message through the host if reload must preserve it.
3. **Render the part in place.** Read `message.parts` from `useChat` in `@ai-sdk/react`. Render only `data-run-progress` with the progress view, keyed by message and part ID; keep optional evidence collapsed and honor the user's toggle when the next update arrives. Use the installed SDK version's `useChat` transport API. Chat `status`, `onFinish`, and `stop()` describe the assistant response stream, not the job. Closing or losing that stream is not job completion or cancellation. If jobs outlive chat responses, reconnect to the authorized run and load its authoritative snapshot before applying newer events; the original stream cannot deliver events after it closes.

## Choose the ReUI component by evidence

| Evidence | Component |
| --- | --- |
| Verified count against a known total | [Progress](https://reui.io/components/progress) with a task name and visible `completed / total` plus units. Give the bar an accessible name. |
| Active work, unknown total | [Spinner](https://reui.io/components/spinner) only if useful, with a short status line; no guessed percentage. |
| Fixed, known sequence | [Stepper](https://reui.io/components/stepper), with explicit labels for the current and completed steps. Keep it non-interactive if the user cannot navigate steps. |
| Parallel or branching work, expandable evidence | [Trace](https://reui.io/components/trace); show observed actions and safe outcomes, not private reasoning. Use words for state even when Trace adds color or motion. |
| One plain milestone, a blocker, or a terminal result | [Marker](https://reui.io/components/marker) or plain text. State what the user can do next; keep the terminal result visible. |

Use free primitives appropriate to the host; [ReUI Agent Activity](https://reui.io/blocks/ai-agents/agent-activity) full-screen blocks are Pro and not required. When React or ReUI is unavailable but you own the renderer, keep the same state contract and use the host's accessible text and disclosure controls. Honor reduced motion and announce meaningful state changes without stealing focus.

**Verify on the intended host:** advance the same run twice and see one card update; interleave a second run without mixing states; simulate unknown totals, a blocker, and a verified failure or completion. If supporting reconnect, replay an older event without regressing the card. Confirm the final state is still readable with motion disabled. A separate demo does not prove embedding works in the target conversation.

Upstream: [Vercel streaming custom data](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data), [`useChat` reference](https://ai-sdk.dev/docs/reference/ai-sdk-ui/use-chat), [UI Message Stream protocol for custom backends](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol).
