@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1
set PY=python
where py >nul 2>nul && set PY=py -3
set MODEL=qwen2.5:1.5b
echo === Round 2B: the 12 proseB runs that failed in RUN_ROUND2 (CLI rejected --style proseB; fixed) ===
echo === plus R=3 replications of the current champion (prompt v2) and the hypervolume ratchet ===
%PY% -B -W ignore -m unittest discover -s tests || goto :fail
echo [Held-out phrasing proseB] v1 / v2 / v3, FCEA
for %%P in (v1 v2 v3) do (
  %PY% -B -m tracedraft run --case K1 --style proseB --selector fcea --adapter ollama --model %MODEL% --prompt %%P
  %PY% -B -m tracedraft run --case F2 --style proseB --selector fcea --adapter ollama --model %MODEL% --prompt %%P
)
echo [Held-out phrasing proseB] top-k with the champion prompt
%PY% -B -m tracedraft run --case K1 --style proseB --selector topk --adapter ollama --model %MODEL% --prompt v2
%PY% -B -m tracedraft run --case F2 --style proseB --selector topk --adapter ollama --model %MODEL% --prompt v2
echo [Replications] champion v2 on prose, two more runs each (R = 3)
for %%R in (2 3) do (
  %PY% -B -m tracedraft run --case K1 --style prose --selector fcea --adapter ollama --model %MODEL% --prompt v2
  %PY% -B -m tracedraft run --case F2 --style prose --selector fcea --adapter ollama --model %MODEL% --prompt v2
)
echo [Verifier] model alone vs layered, held-out phrasing
for %%C in (K1 F2) do (
  %PY% -B -m tracedraft verifier-eval --case %%C --style proseB --adapter ollama --model %MODEL% --llm-mode all
  %PY% -B -m tracedraft verifier-eval --case %%C --style proseB --adapter ollama --model %MODEL% --llm-mode review
)
echo [Ratchet + policy front]
for %%C in (K1 F2) do (
  for %%S in (prose proseB) do (
    %PY% -B -m tracedraft ratchet  --case %%C --style %%S > runs\_ratchet_%%C_%%S_latest.json
    %PY% -B -m tracedraft optimize --case %%C --style %%S --epsilon 0 > nul
  )
)
echo.
echo Done. Decisions are in runs\LEDGER.jsonl (kind = ratchet_decision); latest summaries in runs\_ratchet_*_latest.json
pause
exit /b 0
:fail
echo Self-test failed; nothing was run.
pause
exit /b 1
