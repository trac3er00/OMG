# Vision / Screenshot Auto-Detection

**When:** User mentions screenshots, visual bugs, images, UI comparison, or attaches media.

**Detection signals:**
- "screenshot", "screen", "look at this", "attached image", "visual bug"
- "looks wrong", "looks broken", "compare before/after"
- Korean: "스크린샷", "캡처", "화면", "이미지", "보여"
- User attaches PNG/JPG/GIF files

**Actions in Claude Code CLI:**
1. If screenshot capability is available, capture the current UI state
2. For visual bugs: capture BEFORE making changes
3. After fix: capture AFTER to show comparison
4. For UI review: /OMG:escalate gemini with the screenshot for visual analysis

**Actions when images are attached:**
1. Analyze the image content for context
2. If it shows a UI: identify components, layout, colors
3. If it shows an error: extract the error message and debug
4. If it shows a design mockup: use as reference for implementation

**Integration with Gemini:**
Gemini excels at visual/design tasks. When vision context is detected:
```
/OMG:escalate gemini "Analyze this UI: [description]. Check: layout, accessibility, responsive behavior, visual consistency."
```
