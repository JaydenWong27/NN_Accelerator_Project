"""
train.py -- Train a 2-layer fully connected network on MNIST
=============================================================
This is the ONLY file that uses floating point. Everything after this
(golden model, RTL, firmware) works with INT8 integers only.

The network is dead simple:
    Input:  784 pixels  (28x28 image flattened into a 1D array)
    Layer1: 784 -> 128  (matrix multiply + bias + ReLU)
    Layer2: 128 -> 10   (matrix multiply + bias)
    Output: 10 logits   (highest value = predicted digit)

C++ analogy:
    Think of nn.Linear(784, 128) as a struct holding a 784x128 float
    matrix (weights) and a 128-element float array (biases). The
    forward() call is just:  output[j] = sum(input[i] * W[i][j]) + b[j]
    That is literally what your systolic array will compute in hardware.

FPS analogy:
    Training is like the game's matchmaking algorithm figuring out the
    best weapon stats. You do not need to understand HOW it figures them
    out. You just need the final stats (weights) exported to a file so
    your hardware can use them.
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
import os

# ============================================================
# STEP 1: Define the network architecture
# ============================================================
# This is equivalent to defining a C++ class with two member variables
# (weight matrices) and a forward() method that chains them together.

class MNISTNet(nn.Module):
    def __init__(self):
        super().__init__()

        # nn.Linear(in, out) creates a weight matrix of shape [in x out]
        # and a bias vector of length [out]. Both start as random floats.
        #
        # fc1 holds:
        #   fc1.weight  -> shape [128, 784]  (PyTorch stores transposed)
        #   fc1.bias    -> shape [128]
        self.fc1 = nn.Linear(784, 128)

        # ReLU: if x < 0 then 0, else x.
        # This is the same as:  int relu(int x) { return x > 0 ? x : 0; }
        self.relu = nn.ReLU()

        # fc2 holds:
        #   fc2.weight  -> shape [10, 128]
        #   fc2.bias    -> shape [10]
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        """
        The forward pass. In C++ terms:

            // Flatten the 28x28 image into a 784-element array
            float input[784];
            flatten(image_28x28, input);

            // Layer 1: matmul + bias + relu
            float hidden[128];
            for (int j = 0; j < 128; j++) {
                hidden[j] = bias1[j];
                for (int i = 0; i < 784; i++)
                    hidden[j] += input[i] * weight1[i][j];
                hidden[j] = (hidden[j] > 0) ? hidden[j] : 0;  // ReLU
            }

            // Layer 2: matmul + bias
            float logits[10];
            for (int j = 0; j < 10; j++) {
                logits[j] = bias2[j];
                for (int i = 0; i < 128; i++)
                    logits[j] += hidden[i] * weight2[i][j];
            }
            return logits;

        The systolic array does this exact computation, except with
        INT8 weights and INT8 activations accumulated into INT32.
        """
        # x arrives as shape [batch_size, 1, 28, 28]
        # Flatten to [batch_size, 784]
        x = x.view(x.size(0), -1)

        # Layer 1: multiply by 784x128 weight matrix, add bias, ReLU
        x = self.relu(self.fc1(x))

        # Layer 2: multiply by 128x10 weight matrix, add bias
        x = self.fc2(x)

        return x  # shape [batch_size, 10] -- raw logits, not probabilities


# ============================================================
# STEP 2: Load the MNIST dataset
# ============================================================
# MNIST is 70,000 grayscale handwritten digit images (28x28 pixels).
# 60,000 for training, 10,000 for testing.
# Each pixel is a float between 0.0 (black) and 1.0 (white).
#
# transforms.ToTensor() converts PIL images to float tensors in [0, 1].
# transforms.Normalise((0.5,), (0.5,)) shifts the range to [-1, +1].
# This centring around zero is important for quantisation later because
# it means the weights and activations are roughly symmetric around zero,
# which maps cleanly to signed INT8 [-128, +127].

transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.5,), (0.5,))
])

# Download MNIST if not already present (goes into ./data/ folder)
train_dataset = datasets.MNIST(
    root='./data', train=True, download=True, transform=transform
)
test_dataset = datasets.MNIST(
    root='./data', train=False, download=True, transform=transform
)

# DataLoader handles batching and shuffling.
# batch_size=64 means we process 64 images at a time during training.
# Think of it like processing 64 frames simultaneously in a game engine.
train_loader = torch.utils.data.DataLoader(
    train_dataset, batch_size=64, shuffle=True
)
test_loader = torch.utils.data.DataLoader(
    test_dataset, batch_size=1000, shuffle=False
)


# ============================================================
# STEP 3: Set up training
# ============================================================
model = MNISTNet()

# CrossEntropyLoss: the standard loss function for classification.
# It measures how far the model's predictions are from the correct labels.
# You do not need to understand the maths. Just know: lower = better.
criterion = nn.CrossEntropyLoss()

# Adam optimiser: adjusts the weights to reduce the loss.
# lr=0.001 is the learning rate (how big the adjustment steps are).
# Think of it like a PID controller tuning gain parameters.
optimiser = optim.Adam(model.parameters(), lr=0.001)


# ============================================================
# STEP 4: Training loop
# ============================================================
# An "epoch" is one full pass through all 60,000 training images.
# 5 epochs is usually enough for this simple network to reach 97%+.

NUM_EPOCHS = 5

print("Training started...")
print(f"Network: Linear(784, 128) -> ReLU -> Linear(128, 10)")
print(f"Training images: {len(train_dataset)}")
print(f"Test images: {len(test_dataset)}")
print()

for epoch in range(NUM_EPOCHS):
    model.train()  # Set model to training mode
    running_loss = 0.0
    correct = 0
    total = 0

    for batch_idx, (images, labels) in enumerate(train_loader):
        # images: shape [64, 1, 28, 28] -- 64 images in this batch
        # labels: shape [64] -- the correct digit for each image (0-9)

        # Forward pass: run images through the network
        outputs = model(images)  # shape [64, 10]

        # Compute loss: how wrong are we?
        loss = criterion(outputs, labels)

        # Backward pass: compute gradients (how to adjust each weight)
        optimiser.zero_grad()  # Clear old gradients
        loss.backward()        # Compute new gradients
        optimiser.step()       # Update weights

        # Track accuracy
        _, predicted = torch.max(outputs, 1)  # argmax of 10 logits
        total += labels.size(0)
        correct += (predicted == labels).sum().item()
        running_loss += loss.item()

    # Print epoch summary
    train_acc = 100.0 * correct / total
    avg_loss = running_loss / len(train_loader)
    print(f"Epoch {epoch + 1}/{NUM_EPOCHS}  "
          f"Loss: {avg_loss:.4f}  "
          f"Train accuracy: {train_acc:.1f}%")


# ============================================================
# STEP 5: Evaluate on test set
# ============================================================
model.eval()  # Set model to evaluation mode (disables dropout etc.)
correct = 0
total = 0

with torch.no_grad():  # No need to compute gradients during evaluation
    for images, labels in test_loader:
        outputs = model(images)
        _, predicted = torch.max(outputs, 1)
        total += labels.size(0)
        correct += (predicted == labels).sum().item()

test_acc = 100.0 * correct / total
print(f"\nTest accuracy: {test_acc:.1f}% ({correct}/{total})")

if test_acc < 95.0:
    print("WARNING: Accuracy below 95%. Consider training longer.")
elif test_acc >= 97.0:
    print("Accuracy above 97%. Good to proceed with quantisation.")


# ============================================================
# STEP 6: Save the trained model
# ============================================================
os.makedirs("weights", exist_ok=True)
save_path = "weights/mnist_trained.pth"
torch.save(model.state_dict(), save_path)
print(f"\nModel saved to {save_path}")

# Print weight shapes so you can verify they match your hardware specs
print("\nWeight shapes (verify these match your planning document):")
print(f"  fc1.weight: {model.fc1.weight.shape}  "
      f"(will become 784x128 INT8 = 100,352 bytes)")
print(f"  fc1.bias:   {model.fc1.bias.shape}  "
      f"(will become 128 INT8 = 128 bytes)")
print(f"  fc2.weight: {model.fc2.weight.shape}  "
      f"(will become 128x10 INT8 = 1,280 bytes)")
print(f"  fc2.bias:   {model.fc2.bias.shape}  "
      f"(will become 10 INT8 = 10 bytes)")

total_bytes = 784*128 + 128*10 + 128 + 10
print(f"\nTotal weight RAM needed: {total_bytes:,} bytes "
      f"({total_bytes/1024:.1f} KB)")
print("This must fit in your FPGA block RAM.")
