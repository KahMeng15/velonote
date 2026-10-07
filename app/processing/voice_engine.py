import os
import sys
from io import BytesIO

from pydub import AudioSegment

from pywhispercpp.model import Model as WhisperModel

from app.processing.ai_client import AIClient

MODELS_DIR = os.path.join(os.getcwd(), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

class VoiceEngine:
    def __init__(self):
        self.stt_model = None
        self.tts_model = None
        self.gemini_client = None

    async def initialize(self):
        # Initialize pywhispercpp (will auto-download to ~/.pywhispercpp, but we can set model path if needed,
        # for now let pywhispercpp handle its own download of 'base' or 'tiny')
        if not self.stt_model:
            print("Loading Whisper STT model...")
            # We use 'base' instead of 'tiny' for significantly better transcription accuracy
            self.stt_model = WhisperModel('base', models_dir=MODELS_DIR)

        # Initialize edge-tts (no loading required as it's an API, but we'll mark tts_model as initialized)
        if not self.tts_model:
            print("Using edge-tts for TTS...")
            self.tts_model = "edge-tts"

        # We don't initialize gemini anymore
        print("Voice Engine Initialized.")

    def convert_audio_to_pcm16(self, audio_bytes: bytes) -> str:
        """Converts arbitrary audio bytes (like WebM) to 16kHz PCM WAV mono"""
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        temp_path = os.path.join(MODELS_DIR, "temp_input.wav")
        audio.export(temp_path, format="wav")
        return temp_path

    async def transcribe(self, audio_path: str) -> str:
        # Allow pywhispercpp to auto-detect language to better handle English/Malay code-switching
        segments = self.stt_model.transcribe(audio_path)
        text = " ".join([seg.text for seg in segments])
        return text.strip()

    async def evaluate_context(self, transcription: str, context: str, grading_mode: str = 'lenient', history: list | None = None) -> dict:
        if grading_mode == 'strict':
            strict_text = "Grade STRICTLY. Require exact terminology and complete lists. Do not accept partial matches or missing items."
        else:
            strict_text = "Grade LENIENTLY. If the user captures the basic conceptual essence or provides a partial correct answer, mark it as 'Correct'. Do not penalize for missing terminology, missing items in a list, or loose phrasing."

        history_text = ""
        if history:
            history_text = "--- ONGOING CONVERSATION HISTORY ---\n"
            for h in history:
                role = "Student" if h.get('role') == 'user' else "Tutor (You)"
                history_text += f"{role}: {h.get('text')}\n"
            history_text += "------------------------------------\n"

        prompt = f"""
        You are a friendly, casual human tutor engaging in a natural voice conversation with a student.
        You are currently discussing the following question/topic:
        Topic: {context}

        {history_text}

        Student's latest speech (Note: may contain speech-to-text transcription errors, so interpret charitably): {transcription}

        {strict_text}

        Your Task:
        Look at the Student's latest speech.
        If it's an answer to the original topic, classify into 'Correct', 'Inaccurate', or 'Vague' and coach them naturally.
        If they are asking a follow-up question, chatting, or asking for an explanation (e.g. "explain like I'm 5"), classify as 'Chat' and directly answer them in a helpful, conversational way.

        CRITICAL RULES FOR YOUR VOICE:
        - Speak exactly like a real human tutor having a casual voice call.
        - NEVER use AI boilerplate like "I'd be happy to continue that conversation", "As a tutor", or "It looks like you're...".
        - NEVER summarize what was just said unless explicitly asked.
        - Be highly tolerant of speech-to-text transcription errors (e.g., if the transcription is "explain like I'm in like this old", safely assume they meant "explain like I'm five years old").
        - Do not try to rigidly drag them back to the original topic if they ask a valid follow-up question.
        - Keep it brief, punchy, conversational, and directly to the point.
        - If the student is answering the question and they do not get full marks based on the marking scheme, you MUST explain concisely what they missed or got wrong so they can improve.

        If a Marking Scheme is provided in the topic, and the student is answering, evaluate their answer against the scheme and provide an `awarded_marks` and `max_marks` integer in the JSON. If it's just a chat/follow-up or no scheme is provided, you can omit them.

        Always respond in JSON format: {{"status": "...", "message": "...", "awarded_marks": 0, "max_marks": 0}}
        """

        # Call AI System (Chat category for low latency voice responses)
        client = AIClient(category="chat")
        try:
            # We request raw_output=True and parse JSON manually just like other modules
            response_text = await client.generate_text(
                prompt=prompt,
                max_tokens=150,
                raw_output=True
            )

            # Clean possible markdown wrap from the JSON
            import json
            cleaned = response_text.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)
        except Exception as e:
            print(f"Eval Error: {e}")
            return {"status": "Vague", "message": "Sorry, I couldn't evaluate that locally."}

    async def synthesize(self, text: str) -> bytes:
        import uuid

        import edge_tts

        # We use a natural-sounding US English voice
        communicate = edge_tts.Communicate(text, "en-US-AriaNeural")

        # Use a unique filename to prevent race conditions and file truncation bugs
        unique_id = str(uuid.uuid4())
        out_path = os.path.join(MODELS_DIR, f"temp_out_{unique_id}.mp3")

        try:
            await communicate.save(out_path)
            with open(out_path, "rb") as f:
                audio_bytes = f.read()
            return audio_bytes
        finally:
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except OSError:
                    pass

voice_engine = VoiceEngine()
