# Outside-In — Debug from User's Perspective

**When:** Debugging, investigating issues, or implementing features.

**3 Questions (always ask in this order):**
1. **User sees:** What does the user experience? What error/behavior?
2. **System view:** Where in the architecture does this happen? What's the flow?
3. **Code view:** What specific code is responsible? What does it do wrong?

**Fix from outside in:** Start from the user-visible symptom, trace inward.
Don't start from code and guess what the user sees.

**Apply to features too:** "What will the user do? What will they see? Then: how to implement."
