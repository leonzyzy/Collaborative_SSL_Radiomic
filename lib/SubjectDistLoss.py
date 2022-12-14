import torch
from torch import nn
import numpy as np
import torch.nn.functional as F


class DiscriminationLoss(nn.Module):
    def __init__(self, batch_size, temperature, div):
        super(DiscriminationLoss,self).__init__()
        self.batch_size = batch_size
        self.temperature = temperature
        self.div = div

        self.mask = self.mask_correlated_samples(batch_size)
        self.criterion = nn.CrossEntropyLoss(reduction="sum")
        self.similarity_cosine = nn.CosineSimilarity(dim=2)

        
    def mask_correlated_samples(self, batch_size):
        N = 2 * batch_size
        mask = torch.ones((N, N), dtype=bool)
        mask = mask.fill_diagonal_(0)
        
        for i in range(batch_size):
            mask[i, batch_size + i] = 0
            mask[batch_size + i, i] = 0
        return mask

    def forward(self, z_i, z_j):
        N = 2 * self.batch_size
        z = torch.cat((z_i, z_j), dim=0)
        
        # choose different divergence
        if self.div =='cosine':
            sim = self.similarity_cosine(z.unsqueeze(1), z.unsqueeze(0)) / self.temperature
            
        elif self.div == 'l2':
            sim = 2*(1-self.similarity_cosine(z.unsqueeze(1), z.unsqueeze(0)))/ self.temperature
            
        elif self.div == 'logit':
            z = F.softmax(z,-1)
            sim = torch.mean(z.unsqueeze(1)*(z.unsqueeze(1)/z).log() + (1-z.unsqueeze(1))*((1-z.unsqueeze(1))/(1-z)).log(), dim=2)
             
        elif self.div == 'kl':
            z = F.softmax(z,-1)
            sim = torch.mean(z.unsqueeze(1) * (z.unsqueeze(1)/z).log(),dim = 2)
            
        elif self.div == 'js':
            z = F.softmax(z,-1)
            m = z.unsqueeze(1) + z
            sim = 1/2*(torch.mean(z.unsqueeze(1) * (z.unsqueeze(1)/m).log(),dim = 2) 
                            + torch.mean(z * (m/z.unsqueeze(1)).log(),dim = 2))
            
        elif self.div =='is-dist':
            z = F.softmax(z,-1)
            sim = torch.mean(z.unsqueeze(1)/z-(z.unsqueeze(1)/z).log()-1,dim=2)
            
        elif self.div == 'l2-kl':
            sim1 = 2*(1-self.similarity_cosine(z.unsqueeze(1), z.unsqueeze(0)))/ self.temperature
            z = F.softmax(z,-1)
            m = z.unsqueeze(1) + z
            sim2 = 1/2*(torch.mean(z.unsqueeze(1) * (z.unsqueeze(1)/m).log(),dim = 2) 
                            + torch.mean(z * (m/z.unsqueeze(1)).log(),dim = 2))
            sim = sim1 + 0.1*sim2

        elif self.div =='l2-is':
            sim1 = 2*(1-self.similarity_cosine(z.unsqueeze(1), z.unsqueeze(0)))/ self.temperature
            z = F.softmax(z,-1)
            sim2 = torch.mean(z.unsqueeze(1)/z-(z.unsqueeze(1)/z).log()-1,dim=2)
            sim = sim1 + 0.1*sim2
            
        sim_i_j = torch.diag(sim, self.batch_size)
        sim_j_i = torch.diag(sim, -self.batch_size)
        
        # We have 2N samples, but with Distributed training every GPU gets N examples too, resulting in: 2xNxN
        positive_samples = torch.cat((sim_i_j, sim_j_i), dim=0).reshape(N, 1)
        negative_samples = sim[self.mask].reshape(N, -1)
        
        #SIMCLR
        labels = torch.from_numpy(np.array([0]*N)).reshape(-1).to(positive_samples.device).long() #.float()
        
        logits = torch.cat((positive_samples, negative_samples), dim=1)
        loss = self.criterion(logits, labels)
        loss /= N
        
        return loss
