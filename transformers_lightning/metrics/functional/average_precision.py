import torch


def average_precision(
    preds: torch.Tensor,
    target: torch.Tensor
):
    r"""
    Computes average precision metric for information retrieval,
    as explained here: https://en.wikipedia.org/wiki/Evaluation_measures_(information_retrieval)#Mean_average_precision

    `preds` and `target` should be of the same shape and live on the same device. If not target is true, 0 is returned.

    Args:
        preds: estimated probabilities of each document to be relevant.
        target: ground truth about each document being relevant.
    
    Returns:
        a single-value tensor with the average precision (AP) of the predictions `preds` wrt the labels `target`.

    Example:

        >>> preds = torch.tensor([0.2, 0.3, 0.5])
        >>> target = torch.tensor([True, False, True])
        >>> average_precision(preds, target)
        ... 0.833
    """

    if preds.shape != target.shape or preds.device != target.device: 
        raise ValueError(
            f"`preds` and `target` must have the same shape and be on the same device"
        )

    if target.sum() == 0:
        return torch.tensor([0]).to(preds)

    target = target[torch.argsort(preds, dim=-1, descending=True)]
    positions = torch.arange(1, len(target) + 1, device=target.device)[target > 0]
    res = torch.true_divide((torch.arange(len(positions), device=positions.device) + 1), positions).mean()
    return res
