# Superseded figures

Retained for the record. **None of these is the paper's global-impact
figure.** That is `../fig1_final_model_separated_impacts.png`.

| figure | why it was replaced |
|---|---|
| `fig1_concept_impacts` | Pooled mean abs(impact) across six models with different prediction scales, AND placed all five concepts on one axis. Both are invalid. |
| `fig2_model_concept_heatmap` | Kept models separate, but normalised each model row across all five concepts, so non-commensurable concepts shared one colour scale. |
| `fig1A_commensurable_concept_impacts` | Fixed the concept axis by dropping the non-commensurable concepts, but still pooled a mean across models. |
| `fig1B_grouped_concept_impacts` | Separated the semantic groups, but still pooled a mean across models. |
| `fig2_grouped_semantic_heatmap` | Separated the semantic groups, but still normalised within a model row. |

The common defect in all five is aggregation across models. The final figure
removes it: every point is one valid CSV row, and every panel carries its own
axis.
