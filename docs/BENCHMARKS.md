# Large export benchmark

## Conditions

- Run date: 2026-07-14
- OS: Microsoft Windows 11 Home
- CPU: AMD Ryzen 5 5600 6-Core Processor
- Python: 3.11.9
- Token estimator: `tiktoken:o200k_base` (`tiktoken` 0.13.0)
- Command: `.\.venv\Scripts\python.exe scripts\benchmark_large_export.py --messages <N>`
- Input: deterministic synthetic `conversations.json`, generated in a temporary directory and removed after each run. No real export was used.

`python_tracemalloc_peak_bytes` is the peak allocation tracked by Python's `tracemalloc`; it is **not** total OS RSS. Times include the dashboard and 3-hour report analysis and their generated files. The values are observations on this machine, not performance guarantees for other environments.

## Results

| Messages | Conversations | Input bytes | Elapsed seconds | Python-tracked peak bytes | Output bytes | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 10,000 | 10 | 1,699,981 | 8.114 | 44,601,239 | 122,589 | success |
| 50,000 | 50 | 8,544,341 | 39.959 | 64,862,909 | 437,785 | success |
| 100,000 | 100 | 17,099,791 | 75.833 | 102,348,098 | 828,167 | success |

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_large_export.py --messages 100000 --report-file .\benchmark-result.json
```

The report records input size, conversations, messages, elapsed time, Python-tracked peak memory, generated-output size, token-estimation method, and success/failure. The result file is ignored by Git.
