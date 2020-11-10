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

        print("ids: ", ids)

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






class ExampleIterableDataset(IterableDataset):

    @property
    def length(self):
        return N

    def jump_forward(self, steps: int = 1):
        """ Move reader forward and return last extracted element. """
        row = None
        for i in range(steps):
            row = next(self.reader)
        return row

    """ Init is the same as super class """

    def __iter__(self):
        self.reader = range(100)
        self.is_first = True
        if hasattr(self, 'worker_info'):
            delattr(self, 'worker_info') # it may be necessary to reload info after every epoch...

        self.counter = 0

        if self.is_distributed():
            self.jump_forward(steps=self.get_distributed_id())

        print(torch.utils.data.get_worker_info()); exit()

        return self

    # worker info
    def get_worker_info(self):
        if not hasattr(self, 'worker_info'):
            self.worker_info = torch.utils.data.get_worker_info()
        return self.worker_info

    def is_distributed(self):
        """ Return process id in [0, num_workers-1]! """
        return self.get_worker_info() is not None

    def get_distributed_id(self):
        return self.get_worker_info().id
    
    def get_num_workers(self):
        return self.get_worker_info().num_workers

    def __next__(self):
        """
        Get next element.
        Behaves differently based on whether distributed training is used.
        """
        if self.is_distributed():
            # first step in distributed
            if self.is_first:
                self.is_first = False
                row = self.jump_forward(steps=1)
            # normal step in distributed
            else:
                row = self.jump_forward(steps=self.get_num_workers())

        # normal step in single worker mode
        else:
            row = self.jump_forward(steps=1)

        row_dict = self.get_data_as_dict(row)
        row_dict = self.prepare(row_dict, idx=self.counter)

        self.counter += 1

        return row_dict








class ExampleDataModule(LightningDataModule):

    def __init__(self, hparams):
        super().__init__()
        self.hparams = hparams

    def setup(self, stage=None):
        self.dataset = ExampleIterableDataset(N)

    def train_dataloader(self):
        return DataLoader(self.dataset, batch_size=self.hparams.batch_size)



hparams = Namespace(
    batch_size=4,
    val_batch_size=4,
    test_batch_size=4,
    accumulate_grad_batches=3,
    num_workers=n_cpus,
    dataset_dir='tests/test_data',
    config_dir='tests/test_data',
    cache_dir='cache',
    output_dir='output',
    max_epochs=3,
    max_steps=None,
    max_sequence_length=10,
    gpus=2,
    dataset_style='map',
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