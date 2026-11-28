# Native in-chat forms

Use when a user wants to try an operation interactively or needs to provide structured input. Keep the form and result in the current conversation. An inline diagram or code block is not a form.

1. **Ask for the minimum.** Name what Submit will do and what blank means. Collect only the values needed for one action. Use the host's native form tool (`ask` in omp); for omp send one semantic `<form>` with labeled, named controls and no scripts, styling, or custom submit buttons. If no native form is available, ask for the same values in a chat reply. Do not open a browser.
2. **Interpret the submission.** Validate on receipt; UI hints do not enforce the operation's inputs. Preserve the distinction between an intentional blank and cancellation or timeout. If the host cannot distinguish them, confirm before mapping an empty response to a real operation. Treat every value as data: serialize structured input and pass it as an argument, never interpolate it into executable shell text. Do not collect secrets. A form does not bypass separate authorization or confirmation gates.
3. **Run once and show evidence.** Invoke the owning workflow with the submitted values. Respond with the outcome and the reason in the same chat; distinguish a mismatch or refusal from success. For a repeat request such as “try again,” open a fresh form using the same agreed rule and assumptions. Do not reuse the last submission, write a draft, or repeat an operation automatically.

## Example: try a required-name rule

Send this to the native form tool, not as Markdown for the user to copy:

```html
<form>
  <p><strong>Rules Try: name required</strong></p>
  <p>Enter an invented name, or leave it blank to test a missing name. Submit runs the rule without saving.</p>
  <label>Name <input type="text" name="record_name" placeholder="Example Works"></label>
</form>
```

A submitted blank becomes an empty fields object; a submitted name becomes a fields object with that name. The [Data Onboarding trial](../data-onboarding/MAP.md#visual-rule-trial) owns the rule invocation. Show its actual pass or holdout reason, not a prediction drawn from the form value.
