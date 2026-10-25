# The InGather matcher

The model behind Gather runs. It scores how well a person fits someone's plan, and it scores how well two people in a group fit each other. Serving code is in `app/ml/`, the pipeline around it is `app/services/gather.py`, and training is `ml/train.py`. Exact numbers for the shipped model are in [`app/ml/artifacts/metrics.json`](../app/ml/artifacts/metrics.json).

```bash
uv run python ml/fetch_data.py                # public Meetup.com dataset -> ml/data/ (~700 MB, not committed)
uv run --group train python ml/train.py       # ~5 min -> app/ml/artifacts/
```

Training is seeded, so a rerun on the same data reproduces the shipped artifacts.

## Data

**Real data: the Meetup.com dataset** (Liu et al., *Event-based social networks*, KDD 2012; [github.com/wuyuehit/meetup_dataset](https://github.com/wuyuehit/meetup_dataset)). It has:
- 1.78M members with the topics they picked (median 5, close to how many interests an InGather user types)
- 825k group topic tags
- 10.6M group memberships

It contains no names, messages or locations.

**Rejected: the Columbia speed-dating study** (Fisman & Iyengar). It was tested first and doesn't transfer. Shared interests predict nothing there (AUC 0.50), because romantic first-date decisions are driven by attraction ratings, which InGather doesn't and shouldn't collect.

## What is learned from real data

1. **Interest embeddings.** Topic co-occurrence across all members is turned into PPMI, then reduced with a 64-dimension SVD. That covers the 5,000 most common topics, with typed interests mapped onto them (`app/ml/interests.py`). Example similarities:

   | Pair | Similarity |
   |---|---|
   | ai ~ machine learning | 0.88 |
   | hiking ~ camping | 0.98 |
   | jazz ~ live music | 0.86 |
   | ai ~ knitting | −0.01 |

2. **Interest fit.** The examples are 15,000 groups:
   - **Positives:** a group's topics paired with one of its members' topics.
   - **Negatives:** people from the same local network (members of other groups this group's members joined) who did **not** join.

   This mirrors InGather, where every candidate is already nearby and free, and the question is who fits. Topic lists are subsampled to InGather sizes (2–6 plan interests, 1–8 personal ones). 8% of topics are hidden, so the model also learns to handle interests outside the vocabulary.

## What is simulated

The Meetup data has no activity type, intent, shared event or free-time overlap. These are drawn at random per example. A real positive stays positive only if a simulated "the context works too" draw succeeds. Its logit is −1 + 1.2·same activity + 0.5·same intent + 0.9·same event + 1.4·min(hours, 4)/4 (`CONTEXT_PRIOR` in `train.py`).

**These weights are assumptions, not findings.** Retrain on real InGather outcomes once there are some: passes, accepts and declines are already stored as `ProposalMember` statuses.

## Model

- **Algorithm:** scikit-learn `HistGradientBoostingClassifier`.
- **Monotonic:** more similarity, shared context or shared time never lowers a score.
- **Missing values:** handled natively.
- **Size:** 11 features, about 120 trees.
- **Export:** the trees are saved as plain JSON, and `app/ml/model.py` evaluates them with numpy. The training script fails if the export differs from scikit-learn by more than 1e-6.

## Results (groups never seen in training)

Interest fit on **real** labels, 5-fold cross-validation by group:

| Model | AUC | Top-5 precision |
|---|---|---|
| Old rule: count shared interests | 0.569 | 0.618 |
| Logistic regression | 0.669 | 0.716 |
| **Gradient-boosted trees (shipped)** | **0.671** | **0.716** |

The shipped model's probabilities are well calibrated (expected calibration error 0.002).

**Leakage check.** Meetup members often pick topics while joining a group, so the evaluation was rerun with every topic the group itself lists removed from each person. That leaves only the person's *other* interests. The model still reaches AUC 0.63, so the signal isn't just copied tags.

Full model on held-out groups with simulated context: AUC 0.669, versus 0.616 for the old hand-written rule (shared interests + activity + intent + overlap).

## Limits

- The dataset is from 2012, mostly US Meetup users. Newer interests are reached only through the alias table in `interests.py`.
- Meetup group joining is a proxy for "wants to meet this group". It isn't the same as accepting a small in-person meetup.
- The score ranks fit. It says nothing about safety or trustworthiness and must never be shown as such.
- No protected attributes (age, gender, race, religion) are used or available.
