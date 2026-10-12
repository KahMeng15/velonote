import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.models.db import Exercise
from app.processing.voice_engine import voice_engine
from app.utils.db import get_db
from app.utils.storage import StorageManager

router = APIRouter(prefix="/voice", tags=["Voice"])

@router.get("/tts")
async def get_tts(text: str = Query(...)):
    # Initialize engine if not already done
    if not voice_engine.tts_model:
        await voice_engine.initialize()

    audio_bytes = await voice_engine.synthesize(text)
    return Response(content=audio_bytes, media_type="audio/mpeg")

@router.websocket("/stream/{exercise_id}/{question_id}")
async def voice_stream(websocket: WebSocket, exercise_id: str, question_id: str, db: Session = Depends(get_db)):
    await websocket.accept()

    # Initialize engine if not already done
    if not voice_engine.stt_model:
        await voice_engine.initialize()

    # Get context from DB/Storage
    exercise = db.query(Exercise).filter(Exercise.id == exercise_id).first()
    questions = StorageManager.get_exercise_json(exercise_id) if exercise else []

    question = next((q for q in questions if q.get("id") == question_id), None)
    context = ""
    if question:
        context = f"Question: {question.get('question_text')}\nCorrect Answer/Rubric: {question.get('answer_text')}"
        if question.get("marking_scheme"):
            scheme_str = "\n".join([f"- {c.get('criterion')} ({c.get('max_points')} points)" for c in question.get("marking_scheme", [])])
            context += f"\nMarking Scheme:\n{scheme_str}\nMax Marks: {question.get('max_marks', 1)}"

    audio_chunks = []

    try:
        while True:
            data = await websocket.receive()
            print(f"WS RECEIVED: type={data.get('type')}, keys={list(data.keys())}", flush=True)
            if "bytes" in data:
                audio_chunks.append(data["bytes"])
                # Could perform partial transcription here if needed, but for now we accumulate
            elif "text" in data:
                msg = json.loads(data["text"])
                print(f"WS TEXT MESSAGE: {msg}", flush=True)
                if msg.get("action") == "process":
                    # Process the accumulated audio
                    print(f"Processing audio: {len(audio_chunks)} chunks received.", flush=True)
                    full_audio = b"".join(audio_chunks)
                    if not full_audio:
                        await websocket.send_json({"error": "No audio received"})
                        continue

                    try:
                        # 1. Convert
                        wav_path = voice_engine.convert_audio_to_pcm16(full_audio)

                        # 2. Transcribe
                        transcription = await voice_engine.transcribe(wav_path)
                        await websocket.send_json({"type": "transcription", "text": transcription})

                        # 3. Evaluate
                        grading_mode = msg.get("grading_mode", "lenient")
                        history = msg.get("history", [])
                        print(f"DEBUG VOICE HISTORY: {history}", flush=True)
                        evaluation = await voice_engine.evaluate_context(transcription, context, grading_mode, history)
                        await websocket.send_json({
                            "type": "evaluation",
                            "status": evaluation.get("status"),
                            "message": evaluation.get("message"),
                            "awarded_marks": evaluation.get("awarded_marks"),
                            "max_marks": evaluation.get("max_marks")
                        })

                        # 4. Synthesize TTS if requested
                        if msg.get("response_mode") == "voice":
                            audio_bytes = await voice_engine.synthesize(evaluation.get("message", ""))
                            await websocket.send_bytes(audio_bytes)
                    except Exception as e:
                        await websocket.send_json({"error": str(e)})

                    # Reset buffer for next utterance
                    audio_chunks = []
                elif msg.get("action") == "close":
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Voice WS Error: {e}")
        try:
            await websocket.close()
        except:
            pass
