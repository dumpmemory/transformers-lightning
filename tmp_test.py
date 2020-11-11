import multiprocessing
from argparse import Namespace

import pytest
import pytorch_lightning as pl
import torch
from pytorch_lightning.core.datamodule import LightningDataModule
from torch.utils.data import DataLoader
from torch.utils.data.dataset import Dataset, IterableDataset
from transformers import AdamW, BertTokenizer
from transformers.modeling_bert import (BertConfig,
                                        BertForSequenceClassification)

import transformers_lightning

n_cpus = multiprocessing.cpu_count()
N = 20

class SimpleTransformerLikeModel(transformers_lightning.models.SuperModel):

    def __init__(self, hparams):
        super().__init__(hparams)
        self.lin = torch.nn.Linear(10, 1)

    def training_step(self, batch, batch_idx):
        return {
            "ids": batch['id'],
            "loss": self.lin(batch["data"]).mean()
        }

    def training_epoch_end(self, outputs):
        ids = torch.cat([o['ids'] for o in outputs], dim=0)
        
        gather_ids = [torch.ones_like(ids) for _ in range(torch.distributed.get_world_size())]
        torch.distributed.all_gather(gather_ids, ids)
        print(torch.distributed.get_rank(), ids, gather_ids)
        exit()

        try:
            received = torch.zeros((len(self.datamodule.train_dataset),))
        except TypeError:
            received = torch.zeros((self.datamodule.train_dataset.length,))
        received[ids] = True

        # assert no duplicate element received
        assert len(set(ids.tolist())) == len(ids.tolist()), (
            f"Received {len(ids.tolist())} ids but only {len(set(ids.tolist()))} are unique: {ids}"
        )
        # assert all elements received
        assert all(received), (
            f"({self.trainer.max_steps}) Received not all {len(received)} ids: {received}"
        )

        

    def training_end(self):
        pass

    def validation_step(self, batch, batch_idx):
        kwargs = {k: batch[k] for k in ["input_ids", "attention_mask", "token_type_ids", "labels"]}
        results = self(**kwargs, return_dict=True)
        return results.loss

    def test_step(self, batch, batch_idx):
        kwargs = {k: batch[k] for k in ["input_ids", "attention_mask", "token_type_ids", "labels"]}
        results = self(**kwargs, return_dict=True)
        return results.loss




class ExampleDataset(Dataset):

    def __init__(self, n):
        self.n = n

    def __len__(self):
        return self.n

    def __iter__(self):
        return self

    def __getitem__(self, idx):
        return {
            "id": idx,
            "data": torch.zeros(10)
        }









class ExampleDataModule(LightningDataModule):

    def __init__(self, hparams):
        super().__init__()
        self.hparams = hparams

    def setup(self, stage=None):
        self.dataset = ExampleIterableDataset(N)

    def train_dataloader(self):
        return DataLoader(self.dataset, batch_size=self.hparams.batch_size, num_workers=self.hparams.num_workers)



hparams = Namespace(
    batch_size=4,
    val_batch_size=4,
    test_batch_size=4,
    accumulate_grad_batches=3,
    num_workers=2,
    dataset_dir='tests/test_data',
    config_dir='tests/test_data',
    cache_dir='cache',
    output_dir='output',
    max_epochs=3,
    max_steps=None,
    max_sequence_length=10,
    gpus=2,
    distributed_backend='ddp'
)


# instantiate PL trainer
trainer = pl.Trainer.from_argparse_args(
    hparams,
    profiler='simple',
    logger=None,
    callbacks=[],
)

# instantiate PL model
model = SimpleTransformerLikeModel(hparams)    

# Datasets
datamodule = ExampleDataModule(hparams)

trainer.fit(model, datamodule=datamodule)
