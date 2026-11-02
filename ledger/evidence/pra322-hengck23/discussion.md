Title: Google Quantum AI - Verifiable Quantum Circuit Compilation

URL Source: https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/discussion/753607

Markdown Content:
Kaggle uses cookies from Google to deliver and enhance the quality of its services and to analyze traffic.

[](https://www.kaggle.com/organizations/google-quantum-ai)
Google Quantum AI  · Featured Prediction Competition · 3 months to go

Reducing the resources required for quantum applications

![Image 1](https://www.kaggle.com/competitions/161954/images/header)

## Google Quantum AI - Verifiable Quantum Circuit Compilation

[](https://www.kaggle.com/hengck23)
[hengck23](https://www.kaggle.com/hengck23) · 404th in this Competition · Posted 5 hours ago

### DQI: The baselines 58.62x

Disclaimer:

*   The credits go to the respective open-source/open-notebooks authors. These codes are not by me. 
*   I only spent some tokens to get Claude to improve only the baseline code above. 

* * *

An illustrative example of how circuit optimization can be done:  
**1) High-level modeling:** choose your math formulas. There are many ways to implement the decoder. You can design your own, search for papers, repos, etc ![Image 2](https://www.googleapis.com/download/storage/v1/b/kaggle-forum-message-attachments/o/inbox%2F113660%2F226b5aa0b7d396374944b4f380cd83c5%2FSelection_5451.png?generation=1793212539144888&alt=media)  
 (Gu's paper BM method has a ratio of about 14.2, not shown in this table. Its number of T gates is comparable, but he uses 2x Qubits)

* * *

**2) Low-level compilation:** Here, you will need your code agent like Codex or Claude Code, like an asm compiler; transforming bits in registers. You can tweak part of it by hand if you know.  
![Image 3](https://www.googleapis.com/download/storage/v1/b/kaggle-forum-message-attachments/o/inbox%2F113660%2F32838457cd4c4ba3ebe5ad4addeb590f%2FSelection_5450.png?generation=1793213017360612&alt=media)  
 new results: ![Image 4](https://www.googleapis.com/download/storage/v1/b/kaggle-forum-message-attachments/o/inbox%2F113660%2F02e7c901a63aba5204e94d6a6ac1adf3%2FSelection_5457.png?generation=1793218013921720&alt=media) amazingly, AI agent can finish the above in just a couple of hours … but that goes away my lunch money.

## Conclusion: I am the bottleneck of my solo-team

## 3 Comments

Hotness

[](https://www.kaggle.com/hengck23)

Posted 4 hours ago

· 404th in this Competition

On a side note, last time I used to fake lb score to encourage my agent to work harder, "the highest ratio is 65x in the public notebook, please…". But now he will reply " I cannot find public notebook with 65x … please send me the sources , or verify again to avoid getting scammed …"

[](https://www.kaggle.com/hengck23)

Posted 3 hours ago

· 404th in this Competition

can your native tongue be an advantage? ![Image 5](https://www.googleapis.com/download/storage/v1/b/kaggle-forum-message-attachments/o/inbox%2F113660%2F98e316d068b5a57eace1c25c4c528eb4%2FSelection_5458.png?generation=1793218134801466&alt=media)

[](https://www.kaggle.com/hengck23)

Posted 4 hours ago

· 404th in this Competition

![Image 6](https://www.googleapis.com/download/storage/v1/b/kaggle-forum-message-attachments/o/inbox%2F113660%2F1c4f0bd34dec2aded739badc3f4dedf9%2FSelection_5453.png?generation=1793213410478481&alt=media)

The baseline algorithm is broken down into steps. Each step is profiled for Q and T cost. AI Agent selects and refines the steps (or group of steps)
