"""
test_agent.py
-------------
Manually test the PTY interface — type text in the terminal
and watch it get sent to aider. Verifies the PTY layer works
before we connect voice to it.
"""

import time
from agent_interface import AiderInterface

agent = AiderInterface()
agent.start()

# Give aider 3 seconds to start up and show its welcome prompt
time.sleep(3)

print("\n[voice-aider] PTY ready. Type messages to send to aider (q to quit):")
while True:
    try:
        text = input("> ")
        if text.lower() == "q":
            break
        agent.send(text)
        time.sleep(0.5)  # small pause so aider's response prints before next prompt
    except KeyboardInterrupt:
        break

agent.stop()