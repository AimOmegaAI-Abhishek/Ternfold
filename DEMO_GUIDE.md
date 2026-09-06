# Synthetic sales-call walkthrough

This demonstration uses fictional people and documents. Start from a clean synthetic state with `.\ternfold.ps1 Reset-Demo`, then `.\ternfold.ps1 Start`.

1. Sign in as **Rohan** (`rohan@example.test`). Open order **A-107**. Point out the separate workflow and financial statuses, the named owner Meera, purchasing deadline and precise missing-freight question.
2. Choose **No, add separate freight**, keep ₹5,000, cite the supplier confirmation and save. Existing accepted-order, original-costing and supplier documents remain attached.
3. Sign out and sign in as the **assigned reviewer** (`reviewer@ternfold.test`). Open A-107, compare the material values with the source viewer, confirm inputs and publish reviewed version 1.
4. Show Meera’s comparison: revenue ₹2,00,000; original contribution ₹30,000 / 15.00%; current contribution ₹17,000 / 8.50%. Explain the ₹13,000 decrease as ₹8,000 higher goods cost plus ₹5,000 additional freight.
5. Sign in as **Meera** (`meera@example.test`) and record **Seek revised terms**. Sign back in as Rohan and use **Add synthetic revised quote**. The earlier review and decision remain in history.
6. As the reviewer, confirm the revised evidence and publish version 2. It shows goods ₹1,72,000 plus freight ₹5,000 and contribution ₹23,000 / 11.50%, still below Meera’s 12% floor.
7. As Meera, select **Proceed** and retain the required reason: “Honour the customer commitment; revised supplier terms and delivery confirmed.” The completed screen identifies the owner, reviewed version, rationale and Kavita’s next action.
8. Download the decision summary and click **Copy purchasing handoff**. Optionally add actual freight ₹5,200: reconciliation becomes ₹22,800 / 11.40% while the version-2 decision snapshot remains ₹23,000 / 11.50%.

For recovery examples, open the other seeded cases: missing freight, expired evidence, no adverse change and unsupported scope. To demonstrate a case from scratch, choose **New case**, upload evidence, then use **Enter or correct material inputs**. The reviewer must still confirm and publish it.
