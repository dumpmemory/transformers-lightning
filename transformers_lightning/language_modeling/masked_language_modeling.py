from typing import Tuple
import torch

import transformers
import scipy.stats as st

from transformers_lightning import utils
from transformers_lightning.language_modeling import IGNORE_IDX, LanguageModel
from transformers_lightning.language_modeling.utils import whole_word_tails_mask


class MaskedLanguageModeling(LanguageModel):
    """
    Prepare masked tokens inputs/labels for masked language modeling: 80% MASK, 10% random, 10% original.
    If `weights` are provided, probability of each token to be masked will be weighted in the following way:
        - w are the weights
        - p the probability of masking a token

        probabilities = ( 1 + (w - w_mean) / (w_std * Z_(1 - r/2)) ) -> clipped in [0, 1]

    If `whole_word_masking` is True, either every or no token in a word will be masked. This argument requires
    that `words_tails` are passed to the `__call__` method such that the model can understand which parts of a word
    are tails ('##..'-like tokens). `words_tails` must be a boolean tensor with the same shape as `inputs`
    and be True iff the corresponding tokens starts with `##`. Passing a None `words_tails` will make the model compute
    them, which is expensive. So, for performance reasons we strongly suggest to compute `words_tails` in adapters.


    Usage example:
    >>> import torch
    >>> from transformers import BertTokenizer

    >>> tok = BertTokenizer.from_pretrained('bert-base-cased')
    >>> mlm = MaskedLanguageModeling(tok, whole_word_masking=True)

    >>> input_ids = torch.tensor([tok.encode("test sentence")])
    >>> input_ids
    ... tensor([[ 101, 2774, 5650, 102]])

    >>> masked, labels = mlm(input_ids)
    >>> masked
    ... tensor([[ 101, 103, 5650, 102]]) # 103 mask token id
    >>> labels
    ... tensor([[-100, 2774, -100, -100]]) # -100 = IGNORE_IDX

    >>> # notice that `inputs` are modified by calling `__call__`
    >>> # even if they are returned as a new output. 
    >>> input_ids is masked
    ... True
    """

    def __init__(
        self,
        tokenizer: transformers.PreTrainedTokenizer,
        mlm_probability: float = 0.15,
        reliability: float = 0.05,
        whole_word_masking: bool = False
    ):
        super().__init__(tokenizer)
        self.mlm_probability = mlm_probability
        self.reliability = reliability
        self.whole_word_masking = whole_word_masking

    # TODO: implement whole word masking taking into account average probability of all tokens in a word
    # instead of only of the first token
    def __call__(
        self,
        inputs: torch.Tensor,        
        weights: torch.Tensor = None,
        words_tails: torch.Tensor = None
    ) -> Tuple[torch.LongTensor, torch.LongTensor]:

        if self.tokenizer.mask_token is None:
            raise ValueError(
                "This tokenizer does not have a mask token which is necessary for masked language modeling. "
            )

        device = inputs.device
        labels = inputs.clone()      

        # We sample a few tokens in each sequence for masked-LM training (with probability mlm_probability defaults to 0.15 in Bert/RoBERTa)
        if weights is None:
            probability_matrix = torch.full(labels.shape, fill_value=self.mlm_probability, dtype=torch.float32, device=device)
        else:
            weights = weights.to(device=labels.device)
            z_score = st.norm.ppf(1 - self.reliability / 2)
            probability_matrix = self.mlm_probability * (1 + utils.normalize_standard(weights[labels], dim=-1) / z_score)
            probability_matrix = torch.clip(probability_matrix, min=0, max=1)

        # create whole work masking mask -> True if the token starts with ## (following token in composed words)
        if words_tails is None and self.whole_word_masking:
            words_tails = whole_word_tails_mask(inputs, self.tokenizer)

        if self.whole_word_masking:
            # with whole word masking probability matrix should average probability over the entire word
            probability_matrix.masked_fill_(words_tails, value=0.0)

        special_tokens_mask = [
            self.tokenizer.get_special_tokens_mask(val, already_has_special_tokens=True) for val in labels.tolist()
        ]
        probability_matrix.masked_fill_(torch.tensor(special_tokens_mask, dtype=torch.bool, device=device), value=0.0)

        if self.tokenizer._pad_token is not None:
            padding_mask = labels.eq(self.tokenizer.pad_token_id)
            probability_matrix.masked_fill_(padding_mask, value=0.0)
        masked_indices = torch.bernoulli(probability_matrix).bool()
        labels[~masked_indices] = IGNORE_IDX  # We only compute loss on masked tokens

        # 80% of the time, we replace masked input tokens with tokenizer.mask_token ([MASK])
        indices_replaced = torch.bernoulli(torch.full(labels.shape, 0.8, device=device)).bool() & masked_indices
        inputs[indices_replaced] = self.tokenizer.mask_token_id

        # 10% of the time, we replace masked input tokens with random word
        indices_random = torch.bernoulli(
            torch.full(labels.shape, 0.5, device=device)
        ).bool() & masked_indices & ~indices_replaced
        random_words = torch.randint(len(self.tokenizer), labels.shape, dtype=torch.long, device=device)
        inputs[indices_random] = random_words[indices_random]

        # The rest of the time (10% of the time) we keep the masked input tokens unchanged
        pass
    
        return inputs, labels