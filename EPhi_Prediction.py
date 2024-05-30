import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import random_split, DataLoader
import re
import random
import AEP

def file_to_dict(filename):
    data_dict = {}
    # Regex to match complex numbers
    complex_num_pattern = re.compile(r'[-\s]\d\.\d+.........[^\s]+[\+\-]\d+j')

    with open(filename, 'r') as file:
        current_key = None
        values = []
        for line_number, line in enumerate(file):
            if line_number % 91 == 0:  # Every 91 lines a new block starts
                if current_key is not None:
                    data_dict[current_key] = values
                key_part, complex_numbers = re.split(r'\),\[', line)
                key_part += ')'
                current_key = tuple(map(float, re.findall(r"[-+]?\d*\.\d+|\d+", key_part)))
                values = []
                # Process initial line of complex numbers
                if complex_numbers.strip():
                    complex_matches = complex_num_pattern.findall(complex_numbers)
                    values.extend([complex(num) for num in complex_matches])
            else:
                # Continue collecting values
                line = line.strip().rstrip(']')
                if line.strip():  # Ensure it's not empty
                    complex_matches = complex_num_pattern.findall(line)
                    values.extend([complex(num) for num in complex_matches])

        # Add the last key-value pair
        if current_key is not None:
            data_dict[current_key] = values

    return data_dict

class rEPhiDataset:
    def __init__(self, file_path, transform=None, target_transform=None):
        self.EPhi_positions = file_to_dict(file_path)
        self.positions = torch.tensor([k for k in self.EPhi_positions.keys()], dtype=torch.float)
        self.EPhi = torch.tensor([v for v in self.EPhi_positions.values()], dtype=torch.cfloat)
        self.transform = transform
        self.target_transform = target_transform

    def __len__(self):
        return len(self.EPhi_positions)
    
    def __getitem__(self, idx):
        position = self.positions[idx]
        EPhi = self.EPhi[idx]
        if self.transform:
            EPhi = self.transform(EPhi)
        if self.target_transform:
            position = self.target_transform(position)
        return position, EPhi

class ComplexConvNetwork(nn.Module):
    def __init__(self):
        super(ComplexConvNetwork, self).__init__()
        self.conv1 = nn.Conv1d(in_channels=1, out_channels=8, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(in_channels=8, out_channels=16, kernel_size=3, padding=1)
        # flatten the tensor
        self.fc1 = nn.Linear(181 * 16, 1024)
        self.fc2 = nn.Linear(1024, 32)
        self.fc3 = nn.Linear(32, 362)
        self.fc01 = nn.Linear(4, 32)
        self.fc02 = nn.Linear(32, 181)
        self.fc03 = nn.Linear(181, 362)
        
    def forward(self, x):
        # x = torch.view_as_real(x)  # Converts complex numbers to real, shape becomes (batch_size, 181, 2)
        # x = x.permute(0, 2, 1)
        # # Apply convolutional layers
        # x = F.silu(self.conv1(x))
        # x = F.silu(self.conv2(x))
        # x = x.view(-1, self.num_flat_features(x))
        x = F.celu(self.fc01(x))
        x = F.silu(self.fc02(x))
        x = self.fc03(x)
        return x

    def num_flat_features(self, x):
        size = x.size()[1:]  # 除去批处理维度的其他所有维度
        num_features = 1
        for s in size:
            num_features *= s
        return num_features
    

dataset = rEPhiDataset(file_path='F:\\pythontxtfile\\eEPhi.txt')
# Assuming dataset is a PyTorch Dataset object
total_size = len(dataset)
train_size = int(0.8 * total_size)  # 80% of the dataset
test_size = total_size - train_size  # Remaining 20%
print(f'Train size: {train_size}, Test size: {test_size}')
# Splitting the dataset
train_dataset, test_dataset = random_split(dataset, [train_size, test_size])
train_loader = DataLoader(train_dataset, batch_size=128, shuffle=True)
test_loader = DataLoader(test_dataset, batch_size=128, shuffle=False)

# Instantiate the model, loss function, and optimizer

criterion = torch.nn.MSELoss()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = ComplexConvNetwork().to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

def train_model(dataloader, model, criterion, device, optimizer, num_epochs):
    model.train()
    for epoch in range(num_epochs):
        running_loss = 0.0
        for position, EPhi in dataloader:
            position, EPhi = position.to(device), EPhi.to(device)

            optimizer.zero_grad()
            
            # Forward pass
            outputs = model(position)
            loss = criterion(outputs, torch.view_as_real(EPhi).view(-1, 362))

            # Backward and optimize
            loss.backward()
            optimizer.step()

            running_loss += loss.item()

        print(f'Epoch [{epoch+1}/{num_epochs}], Loss: {running_loss/len(dataloader):.4f}')

def test_model(dataloader, model, criterion, device):
    model.eval()  # Set the model to evaluation mode
    total_loss = 0.0
    total_samples = 0

    with torch.no_grad():  # No gradients needed
        for position, EPhi in dataloader:
            position = position.to(device)
            EPhi = EPhi.to(device)

            outputs = model(position)
            loss = criterion(outputs, torch.view_as_real(EPhi).view(-1, 362))

            total_loss += loss.item() * position.size(0)
            total_samples += position.size(0)

    average_loss = total_loss / total_samples
    print(f'Average Loss: {average_loss:.4f}')

num_epochs = 50  # Define the number of epochs for training
train_model(train_loader, model, criterion, device, optimizer, num_epochs)
test_model(test_loader, model, criterion, device)

positionlist = [0]
for i in range(17):
    if not i == 0:
        positionlist.append(positionlist[i-1]+(random.uniform(15,30)))
rEPhi_sim = AEP.validateAEP(positionlist)

distribution = AEP.positionlist2positionDistribution(positionlist)

rep = [complex(0,0)] * 181
for value in rEPhi_sim.values():
    rep += value['rEPhi']
rep = torch.view_as_real(torch.tensor(rep).to(device)).view(362)

rEPhi_model = torch.tensor([0] * 362, dtype=torch.float).to(device)
for value in distribution.values():
    rEPhi_model += model(torch.tensor(value, dtype=torch.float).to(device))

AEPcriterion = criterion(rEPhi_model, rep)