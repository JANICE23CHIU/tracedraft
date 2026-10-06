@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1
set PY=python
where py >nul 2>nul && set PY=py -3
set MODEL=qwen2.5:1.5b
set MIN_GAIN=0.10
echo === Round 3: pre-registered held-out phrasing proseC (see docs\PREREGISTRATION_proseC.md) ===
%PY% -B -W ignore -m unittest discover -s tests || goto :fail
%PY% -B data\synthetic\generate.py --check || goto :fail
echo [P3/P4] champion prompt v2, R = 3, plus v1 and v3 once, FCEA
for %%C in (K1 F2) do (
  for %%R in (1 2 3) do %PY% -B -m tracedraft run --case %%C --style proseC --selector fcea --adapter ollama --model %MODEL% --prompt v2
  %PY% -B -m tracedraft run --case %%C --style proseC --selector fcea --adapter ollama --model %MODEL% --prompt v1
  %PY% -B -m tracedraft run --case %%C --style proseC --selector fcea --adapter ollama --model %MODEL% --prompt v3
)
echo [Verifier] model-assisted, proseC
for %%C in (K1 F2) do %PY% -B -m tracedraft verifier-eval --case %%C --style proseC --adapter ollama --model %MODEL% --llm-mode review
echo [Ratchet + policy front] min-gain fixed from the R = 3 replicate spread on prose = 0.10: the largest relative HV range among R = 3 replicates was 9.4%% (K1)
for %%C in (K1 F2) do (
  for %%S in (prose proseB proseC) do (
    %PY% -B -m tracedraft ratchet  --case %%C --style %%S --min-gain %MIN_GAIN% > runs\_ratchet_%%C_%%S_mg_latest.json
    %PY% -B -m tracedraft optimize --case %%C --style %%S --epsilon 0 > nul
  )
)
echo.
echo Done. Results are appended to runs\LEDGER.jsonl
pause
exit /b 0
:fail
echo Self-test or data check failed; nothing was run.
pause
exit /b 1
