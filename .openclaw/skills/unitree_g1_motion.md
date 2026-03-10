---
name: unitree_g1_motion
description: Execute physical motions on the Unitree G1 robot by sending text commands to the local Sim2Real API via curl.
homepage: http://127.0.0.1:8080
metadata:
  {
    "openclaw":
      {
        "emoji": "🤖",
        "requires": { "bins": ["curl"] },
        "install": []
      },
  }
---

# unitree_g1_motion

Use `unitree_g1_motion` ONLY when the user explicitly requests the physical robot to perform a bodily action, movement, or gesture (e.g., walking, waving, crouching).
Do NOT use this tool for normal text responses. This tool translates natural language directly into physical robot movement.

Safety

- Always extract the core action and translate it into a concise English phrase (e.g., "wave right hand", "walk forward").
- Do not execute actions that are physically impossible or highly dangerous for a bipedal robot.

Execute Motion (Linux CLI)

- Use the `curl` command via the `exec` tool to send the action to the local 8080 port.
- Example command:
  `curl -s -X POST http://127.0.0.1:8080/generate_and_play -H "Content-Type: application/json" -d '{"action_text": "wave right hand"}'`

Notes

- The API endpoint is strictly `http://127.0.0.1:8080/generate_and_play`.
- Wait for the API to return a success response before confirming the action to the user.
