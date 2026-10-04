# Gemma 4 Reasoning Models Integration

This document summarizes the findings and provides a guide on how to use the **Gemma 4** reasoning models within velonote.

## 🚀 Overview
Gemma 4 is a reasoning-centric model series from Google. Unlike standard models, Gemma 4 performs internal "thinking" before producing a final answer. This makes it ideal for complex study materials, difficult problem-solving, and deep logical analysis.

## ✅ Verified Models
The following models have been tested and verified to work with the current implementation:

1.  **`models/gemma-4-31b-it`**: The larger, highly capable reasoning model.
2.  **`models/gemma-4-26b-a4b-it`**: A Mixture-of-Experts (MoE) variant that provides a balance of speed and reasoning depth.

## ⚙️ Configuration

To use Gemma 4, update your `.env` file or the Admin Dashboard settings:

```env
# Set the provider to gemini (Tier 1)
GLOBAL_AI_TIER1_PROVIDER=gemini

# Choose one of the verified models
GLOBAL_AI_TIER1_MODEL=models/gemma-4-26b-a4b-it

# Ensure your Gemini API Key is set
GLOBAL_AI_TIER1_API_KEY=your_api_key_here

# (Optional) Set reasoning depth: low, medium, or high
GLOBAL_AI_TIER1_REASONING_LEVEL=medium
```

## 🧠 How Reasoning Works in velonote

### 1. Reasoning Depth Injection
The `AIClient` automatically detects when a Gemma 4 model is in use and injects the `REASONING DEPTH` instruction into your prompts. This guides the model's internal "thinking" process.

### 2. Automatic Filtering
Gemma 4 outputs its reasoning process using special tokens (e.g., `<|thought|>` or `<|channel|>thought`). 
**velonote is equipped with a filtering layer** in `app/processing/ai_client.py` that identifies these tokens and strips them out before the response reaches the UI. 
*   **Result:** You get a clean, polished answer without the internal "messy" thinking process visible.

### 3. Increased Timeouts
Because Gemma 4 "thinks" before it speaks, response times may be longer than standard models (like Gemini 1.5 Flash). The application is configured with a 240-second timeout to accommodate this extra processing time.

## 💡 Best Practices

*   **Be Patient:** If a response takes 10-20 seconds, it is likely the model performing complex reasoning.
*   **Use for Hard Subjects:** Use Gemma 4 for subjects like Mathematics, Physics, Logic, or complex Law cases where standard AI might hallucinate.
*   **Prompt Markers:** If you want very specific formatting, use markers like `===START===` in your prompt. Gemma 4 is highly compliant with markers after finishing its reasoning phase.

## 🛠️ Troubleshooting

| Issue | Solution |
| :--- | :--- |
| **"Timeout" Error** | Try to simplify the question or check if the model is currently overloaded. |
| **Reasoning tags visible** | Ensure your `AIClient` is updated to the latest version which includes the `is_gemma4` filtering logic. |
| **"Model not found"** | Verify the model name matches exactly (e.g., `models/gemma-4-31b-it`). |

---
*Last Updated: May 2026*
