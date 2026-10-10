# Kickoff email (Freya team)

Hi Faruk,

Thanks for joining the kickoff! Here is everything you need to start.

Hackathon page (task, scoring, rules, timeline): https://www.freyavoice.ai/hackathon
Starter kit, version 3 (briefs, docs, 13 practice customers, an example agent and an example builder): https://www.freyavoice.ai/hackathon/build-the-builder-v3.zip
The kit has a version number in its file name and at the top of README.md. If we update it, we will email you the new version. Read README.md first, it has a ten-minute start.

Your Freya API key: Sign in at https://staging-app.freyavoice.ai and create a key in your workspace under API keys. Put it in env.sh as FREYA_API_KEY.

The bank's tool API: The phone agent calls it during a call. Its description is in the kit at tools/openapi.json. You pick your own team key, any secret of 16 or more characters, and use the same one every time.

Starter workflow: Your workspace already has "Freya Bank Collections Base". Its test variables hold a practice customer, so you can start a chat right away. The same agent is in the kit as examples/base-agent.json.

Kickoff recording: https://fathom.video/share/SCFTpw9gPFqxxEqk49PbM3HFjSros35m

Timeline: Hidden briefs open on Sunday at 17:00 UTC (20:00 Istanbul). Submissions close on Sunday at 20:00 UTC (23:00 Istanbul). We will send the submission steps before the hidden briefs open.

Good to know:
- You can work solo or in a team of two.
- One practice simulation runs at a time per workspace.
- Any tool is fine for your builder: Claude Code, Codex, your own code. Keep the builder's trace, we ask for it with your submission.

Background reading, the benchmark that inspired this format: https://arxiv.org/pdf/2609.04611
