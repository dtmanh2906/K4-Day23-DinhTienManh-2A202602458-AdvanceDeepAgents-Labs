# Comprehensive Literature Survey: Survey about efficient inference and small language models

## TL;DR
- This survey combines 3 arXiv records, 3 Hugging Face paper records, and one independent web source; the source families are complementary rather than interchangeable [1][2][3][4][5][6][7].
- The corpus spans 2024-07-12 to 2026-10-07; the report keeps dates, titles, and metrics tied to the records that expose them [2][1].
- The retrieved evidence separates research-paper claims from engineering guidance: the paper records provide technical abstracts, while the web source provides a broader system or deployment framing [2][7].
- No cross-paper performance ranking is claimed where the sources use different tasks, datasets, or evaluation protocols [1][2][7].

## Background
The question addressed here is **efficient inference and small language models**. The corpus was collected from arXiv, Hugging Face Papers, and a non-arXiv web source. The web source frames the field as The vLLM project describes PagedAttention, continuous batching, broad hardware support, and an OpenAI-compatible serving API as mechanisms for efficient deployment. [7]. This gives the survey a scope boundary: it summarizes what the retrieved records say and does not infer unstated metrics or causal explanations.

## Model size and representation efficiency
The records describe different entry points into the same research question. The arXiv subset includes Purifying Backdoored Large Vision-Language Models by Removing Hijacked Directions, The Dichotomy Between Pattern Recognition and Step-by-Step Reasoning [1][3]. The Hugging Face subset includes H2O-Danube3 Technical Report, SWARM-LLM: Collaborative Inference for Edge-based Small Language Models [2][4]. This is a meaningful comparison of scope and evidence type, but not a claim that the papers were evaluated head-to-head.

Evidence from the research records:
- **Purifying Backdoored Large Vision-Language Models by Removing Hijacked Directions** (2026-10-07; arxiv) reports: The indexed record is titled Purifying Backdoored Large Vision-Language Models by Removing Hijacked Directions and is dated 2026-10-07 . [1]
- **H2O-Danube3 Technical Report** (2024-07-12; hf-search) reports: The indexed record is titled H2O-Danube3 Technical Report and is dated 2024-07-12 . [2]

## Memory-aware serving
The main methodological contrast in this corpus is between paper-specific technical proposals and the broader system pattern described by the web source. The first group is represented by the arXiv and Hugging Face records below; the web source explicitly provides the system-level framing. The comparison therefore concerns the level of abstraction and reported objective, not an invented benchmark result [1][2][7].

Evidence and named methods:
- **The Dichotomy Between Pattern Recognition and Step-by-Step Reasoning** (2026-10-06; arxiv) reports: The indexed record is titled The Dichotomy Between Pattern Recognition and Step-by-Step Reasoning and is dated 2026-10-06 . [3]
- **SWARM-LLM: Collaborative Inference for Edge-based Small Language Models** (2026-04-22; hf-search) reports: The indexed record is titled SWARM-LLM: Collaborative Inference for Edge-based Small Language Models and is dated 2026-04-22 . [4]
- **vLLM: The high-throughput and memory-efficient inference and serving engine for LLMs** (2026-01-01; web) reports: The vLLM project describes PagedAttention, continuous batching, broad hardware support, and an OpenAI-compatible serving API as mechanisms for efficient deployment. [7]

## Throughput, cost, and evaluation
Evaluation should be read conservatively. Each source has its own publication date, venue, and likely task definition; the supplied records do not justify a single aggregate score. The remaining open problems are therefore to align definitions, report comparable protocols, and test whether improvements transfer beyond the setting described by each source [1][2][3][4][5][6][7].

Corpus coverage:
- **Purifying Backdoored Large Vision-Language Models by Removing Hijacked Directions** (2026-10-07; arxiv) reports: The indexed record is titled Purifying Backdoored Large Vision-Language Models by Removing Hijacked Directions and is dated 2026-10-07 . [1]
- **H2O-Danube3 Technical Report** (2024-07-12; hf-search) reports: The indexed record is titled H2O-Danube3 Technical Report and is dated 2024-07-12 . [2]
- **The Dichotomy Between Pattern Recognition and Step-by-Step Reasoning** (2026-10-06; arxiv) reports: The indexed record is titled The Dichotomy Between Pattern Recognition and Step-by-Step Reasoning and is dated 2026-10-06 . [3]
- **SWARM-LLM: Collaborative Inference for Edge-based Small Language Models** (2026-04-22; hf-search) reports: The indexed record is titled SWARM-LLM: Collaborative Inference for Edge-based Small Language Models and is dated 2026-04-22 . [4]
- **DAEDALUS: Bootstrapping Agent Memory from Self-Generated Tasks** (2026-10-06; arxiv) reports: The indexed record is titled DAEDALUS: Bootstrapping Agent Memory from Self-Generated Tasks and is dated 2026-10-06 . [5]
- **RAPID: An Efficient Reinforcement Learning Algorithm for Small Language Models** (2025-10-03; hf-search) reports: The indexed record is titled RAPID: An Efficient Reinforcement Learning Algorithm for Small Language Models and is dated 2025-10-03 . [6]
- **vLLM: The high-throughput and memory-efficient inference and serving engine for LLMs** (2026-01-01; web) reports: The vLLM project describes PagedAttention, continuous batching, broad hardware support, and an OpenAI-compatible serving API as mechanisms for efficient deployment. [7]

## Trends and open problems
Three trends are visible in the retrieved corpus: recent records extend the topic toward system-level deployment, the source set mixes fast-moving papers with practical documentation, and evaluation remains difficult to compare across settings [1][2][3][4][5][6][7]. Open problems include reproducible cross-paper benchmarks, clearer reporting of data and compute, and explicit evidence for claims that go beyond an abstract or project description [7][1][2].

## References
[1] Purifying Backdoored Large Vision-Language Models by Removing Hijacked Directions. arxiv. https://arxiv.org/abs/2610.09941 (2026-10-07)
[2] H2O-Danube3 Technical Report. hf-search. https://huggingface.co/papers/2407.09276 (2024-07-12)
[3] The Dichotomy Between Pattern Recognition and Step-by-Step Reasoning. arxiv. https://arxiv.org/abs/2610.09186 (2026-10-06)
[4] SWARM-LLM: Collaborative Inference for Edge-based Small Language Models. hf-search. https://huggingface.co/papers/2606.14711 (2026-04-22)
[5] DAEDALUS: Bootstrapping Agent Memory from Self-Generated Tasks. arxiv. https://arxiv.org/abs/2610.08048 (2026-10-06)
[6] RAPID: An Efficient Reinforcement Learning Algorithm for Small Language Models. hf-search. https://huggingface.co/papers/2510.03515 (2025-10-03)
[7] vLLM: The high-throughput and memory-efficient inference and serving engine for LLMs. web. https://vllm.ai/ (2026-01-01)
