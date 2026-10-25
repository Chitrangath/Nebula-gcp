# Nebula GPU Provider Setup: Windows, WSL2, CUDA, and Worker

This guide prepares a Windows machine with an NVIDIA GPU to run a Nebula
provider Worker. It is written for a fresh machine and should be completed in
order.

The provider uses the public dApp for registration, but the Worker runs locally
so it can access the provider's GPU. Do not paste private keys or node API keys
into GitHub, browser URLs, screenshots, or chat.

## What you need

- Windows 11, or a supported Windows 10 installation with virtualization
  enabled in BIOS/UEFI
- NVIDIA GPU with a current Windows driver and WSL2 CUDA support
- Administrator access to Windows
- At least 8 GB system RAM recommended
- At least 12 GB free disk space recommended
- A separate provider wallet for the testnet demonstration
- The provider's registered node ID, one-time API key, and Worker signer key

## 1. Install or update WSL2 and Ubuntu

Open **PowerShell as Administrator** on Windows and run:

```powershell
wsl --install -d Ubuntu-24.04
```

If WSL is already installed, update it instead:

```powershell
wsl --update
wsl --set-default-version 2
wsl --list --verbose
```

The Ubuntu distribution must show version `2`. If it shows version `1`, convert
it from Administrator PowerShell:

```powershell
wsl --set-version Ubuntu-24.04 2
```

Restart Windows if the installer requests it. Launch **Ubuntu** from the Start
menu and create the Linux username and password. This password is only for the
local Ubuntu environment; it is not a Nebula credential.

## 2. Install the NVIDIA Windows driver

On Windows, install the current NVIDIA driver for the RTX GPU from NVIDIA's
official driver page:

<https://www.nvidia.com/Download/index.aspx>

Choose the correct GPU and Windows version, install the driver, and restart
Windows. The driver is installed on Windows; do not install a separate Linux
GPU driver inside WSL for this setup.

After restarting, open Ubuntu and verify that the GPU is visible:

```bash
nvidia-smi
```

You should see the GPU name, driver version, and memory. If `nvidia-smi` is not
found or reports that no device is available:

1. Confirm Docker Desktop or other software is not blocking WSL GPU access.
2. Run `wsl --update` in Administrator PowerShell.
3. Restart Windows and retry `nvidia-smi` in Ubuntu.
4. Confirm virtualization is enabled in BIOS/UEFI.

Do not continue until `nvidia-smi` works.

## 3. Prepare Ubuntu packages

Run the following **inside the Ubuntu terminal**, not PowerShell:

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl git python3 python3-venv python3-pip
```

Verify the basic tools:

```bash
git --version
python3 --version
curl --version
nvidia-smi
```

## 4. Clone the Nebula provider branch

Still inside Ubuntu:

```bash
cd ~
git clone -b feat/gcp-demo-host https://github.com/Chitrangath/Nebula-gcp.git
cd ~/Nebula-gcp
```

The provider does not need to run the frontend or deploy the backend locally.
The provider only needs the Worker code and the public dApp in a browser.

## 5. Install and verify the Worker environment

Run the repository bootstrap script:

```bash
./scripts/provider_wsl_bootstrap.sh --install
```

This installs `uv`, creates `worker/.venv`, installs the pinned CUDA Worker
dependencies, and checks that PyTorch can use the GPU. The first installation
may take several minutes because CUDA-enabled PyTorch packages are large.

Verify without changing anything:

```bash
./scripts/provider_wsl_bootstrap.sh --check
```

The check must report successful NVIDIA and PyTorch CUDA access. You can also
run the direct verification:

```bash
worker/.venv/bin/python -c \
"import torch; print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No GPU')"
```

## 6. Register the provider node in the public dApp

Open:

<https://nebula-gcp.vercel.app>

1. Connect the provider wallet.
2. Open the Provider section.
3. Register a GPU node.
4. Record the displayed node UUID and one-time API key in a local password
   manager.
5. Configure a dedicated Worker signer key pair. Record only its public
   address in the dApp; keep the private key on this machine.

The provider wallet and Worker signer should normally be different addresses.

## 7. Start the provider Worker

From Ubuntu, run:

```bash
./scripts/demo008_provider_worker_wizard.sh --check
./scripts/demo008_provider_worker_wizard.sh --plan
./scripts/demo008_provider_worker_wizard.sh --run
```

The wizard will request the Cloud Run API origin, node UUID, node API key,
Worker signer private key, contract address, and approved model artifact URL.
Enter these values directly into the hidden prompts. Never echo them into a
terminal transcript.

Check the Worker:

```bash
./scripts/demo008_provider_worker_wizard.sh --status
```

After the first authenticated heartbeat, the node should change from `pending`
to `online` in the provider dashboard/network page.

## 8. Run a provider test

Keep the Worker running. In a separate browser profile, use an AI-user wallet
to submit one ResNet50 or BERT job from the prepared examples in
[`../demo-data/`](../demo-data/). The provider Worker should receive a lease,
execute the model, upload the result and proof, and return to an idle state.

When the demonstration is finished:

```bash
./scripts/demo008_provider_worker_wizard.sh --stop
```

## Troubleshooting

### `nvidia-smi` is missing

The Windows NVIDIA driver or WSL GPU integration is incomplete. Fix Windows
driver/WSL2 first; do not install a random Linux driver inside Ubuntu.

### PyTorch reports `CUDA: False`

Run `wsl --update` from Administrator PowerShell, restart Windows, and rerun
the bootstrap script. Confirm the GPU is visible with `nvidia-smi`.

### Node remains `pending`

The Worker is not sending a valid heartbeat. Check the Worker status/log,
confirm the node UUID and API key, verify the Cloud Run API origin, and confirm
that the Worker signer is configured correctly.

### The Worker starts and exits

Inspect the protected Worker log from the wizard status output. Common causes
are a missing BERT vocabulary, an invalid model URL/hash, insufficient disk
space, or a CUDA/PyTorch mismatch.

### Credential safety

Rotate a node API key immediately if it is exposed. Never commit the generated
Worker environment file, node API key, signer private key, wallet private key,
database URL, JWT secret, or RPC credentials.
