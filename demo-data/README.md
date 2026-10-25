# Nebula demonstration inputs

Use these files at https://nebula-gcp.vercel.app/user/submit.

Each submission runs inference on **one image or one text review**. The current
application does not accept a ZIP, folder, CSV, or batch of examples as one job.
These examples exercise existing trained models; they do not train a model.

## ResNet50: upload an image

Select **ResNet50 · Image classification**, then upload either example:

| File | Purpose |
| --- | --- |
| `resnet50/01-dog.jpg` | A dog photograph from the official Torchvision gallery |
| `resnet50/02-dog.jpg` | A different dog photograph to demonstrate a second input |

The result contains the model's top ImageNet class indices and probabilities.
Predictions are computed by the GPU Worker. A particular breed, score, or class
index is not guaranteed by this example pack.

Both images are unmodified downloads. The Torchvision source URLs are recorded
in `SOURCES.md`; image rights remain with their respective owners.

## BERT: paste a review

Select **BERT · Review sentiment (1–5 stars)**. Open a `.txt` file below and
paste its contents into **Text to analyse**. The current website uses a text
box for BERT rather than a file picker.

| File | Intended sentiment |
| --- | --- |
| `bert/01-positive.txt` | Strongly positive |
| `bert/02-negative.txt` | Strongly negative |
| `bert/03-mixed.txt` | Mixed / moderate |
| `bert/04-positive-french.txt` | Positive French review |
| `bert/05-negative-spanish.txt` | Negative Spanish review |
| `bert/06-positive-german.txt` | Positive German review |

These are original synthetic product reviews and contain no personal data.
All are under the website's 510-character limit. Intended sentiment is a
presentation aid, not a promised model prediction; BERT returns its actual
1–5-star score and probability distribution.

## Suggested presentation order

1. Show the Network page with the available GPU providers.
2. Submit `resnet50/01-dog.jpg`; review the price and sign the wallet requests.
3. Wait for completion, then show the result, proof status, explorer links,
   settlement, and provider credit.
4. Submit the contents of `bert/01-positive.txt` as a new BERT job.
5. Optionally submit `bert/02-negative.txt` to compare sentiment results.
6. Use the second dog image or a multilingual review for further examples.

Either compatible provider can execute either model. One provider can execute
these jobs sequentially. Keep the owner runners and provider Worker processes
running throughout the presentation. Each funded submission consumes test
USDC and test ETH; no funded jobs are created by opening these files.

`SHA256SUMS` records the downloaded images and review files. From this directory,
run `sha256sum --check SHA256SUMS` to verify the pack.
