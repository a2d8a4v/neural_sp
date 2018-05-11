#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Define evaluation method by Character Error Rate (CSJ corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import re
from tqdm import tqdm
import pandas as pd

from utils.io.labels.character import Idx2char
from utils.evaluation.edit_distance import compute_wer


def do_eval_cer(models, dataset, beam_width, max_decode_len,
                eval_batch_size=None,  length_penalty=0,
                progressbar=False, temperature=1):
    """Evaluate trained model by Character Error Rate.
    Args:
        models (list): the models to evaluate
        dataset: An instance of a `Dataset' class
        beam_width: (int): the size of beam
        max_decode_len (int): the length of output sequences
            to stop prediction when EOS token have not been emitted.
            This is used for seq2seq models.
        eval_batch_size (int, optional): the batch size when evaluating the model
        progressbar (bool, optional): if True, visualize the progressbar
        length_penalty (float, optional):
        temperature (int, optional):
    Returns:
        wer (float): Word error rate
        cer (float): Character error rate
        df_wer_cer (pd.DataFrame): dataframe of substitution, insertion, and deletion
    """
    # Reset data counter
    dataset.reset()

    if models[0].model_type in ['ctc', 'attention']:
        idx2char = Idx2char(vocab_file_path=dataset.vocab_file_path)
    else:
        idx2char = Idx2char(vocab_file_path=dataset.vocab_file_path_sub)

    cer, wer = 0, 0
    sub_char, ins_char, del_char = 0, 0, 0
    sub_word, ins_word, del_word = 0, 0, 0
    num_words, num_chars = 0, 0
    if progressbar:
        pbar = tqdm(total=len(dataset))  # TODO: fix this
    while True:
        batch, is_new_epoch = dataset.next(batch_size=eval_batch_size)

        # Decode
        if len(models) > 1:
            assert models[0].model_type in ['ctc']
            for i, model in enumerate(models):
                probs, x_lens, perm_idx = model.posteriors(
                    batch['xs'], batch['x_lens'], temperature=temperature)
                if i == 0:
                    probs_ensenmble = probs
                else:
                    probs_ensenmble += probs
            probs_ensenmble /= len(models)

            best_hyps = models[0].decode_from_probs(
                probs_ensenmble, x_lens, beam_width=beam_width)

            ys = batch['ys'][perm_idx]
            y_lens = batch['y_lens'][perm_idx]
            task_index = 0
        else:
            model = models[0]
            # TODO: fix this

            if model.model_type in ['ctc', 'attention']:
                best_hyps, _, perm_idx = model.decode(
                    batch['xs'], batch['x_lens'],
                    beam_width=beam_width,
                    max_decode_len=max_decode_len,
                    length_penalty=length_penalty)
                ys = batch['ys'][perm_idx]
                y_lens = batch['y_lens'][perm_idx]
                task_index = 0
            else:
                best_hyps, _, perm_idx = model.decode(
                    batch['xs'], batch['x_lens'],
                    beam_width=beam_width,
                    max_decode_len=max_decode_len,
                    length_penalty=length_penalty,
                    task_index=1)
                ys = batch['ys_sub'][perm_idx]
                y_lens = batch['y_lens_sub'][perm_idx]
                task_index = 1

        for b in range(len(batch['xs'])):

            ##############################
            # Reference
            ##############################
            if dataset.is_test:
                str_ref = ys[b][0]
                # NOTE: transcript is seperated by space('_')
            else:
                # Convert from list of index to string
                str_ref = idx2char(ys[b][:y_lens[b]])

            ##############################
            # Hypothesis
            ##############################
            str_hyp = idx2char(best_hyps[b])
            if 'attention' in model.model_type:
                str_hyp = str_hyp.split('>')[0]
                # NOTE: Trancate by the first <EOS>

            # Remove garbage labels
            str_ref = re.sub(r'[@>]+', '', str_ref)
            str_hyp = re.sub(r'[@>]+', '', str_hyp)
            # NOTE: @ means <sp>

            # Remove consecutive spaces
            str_ref = re.sub(r'[_]+', '_', str_ref)
            str_hyp = re.sub(r'[_]+', '_', str_hyp)

            if dataset.label_type == 'kanji_wb' or (task_index > 0 and dataset.label_type_sub == 'kanji_wb'):
                # Compute WER
                try:
                    wer_b, sub_b, ins_b, del_b = compute_wer(
                        ref=str_ref.split('_'),
                        hyp=str_hyp.split('_'),
                        normalize=False)
                    wer += wer_b
                    sub_word += sub_b
                    ins_word += ins_b
                    del_word += del_b
                    num_words += len(str_ref.split('_'))
                except:
                    pass

            # Compute CER
            try:
                cer_b, sub_b, ins_b, del_b = compute_wer(
                    ref=list(str_ref.replace('_', '')),
                    hyp=list(str_hyp.replace('_', '')),
                    normalize=False)
                cer += cer_b
                sub_char += sub_b
                ins_char += ins_b
                del_char += del_b
                num_chars += len(str_ref.replace('_', ''))
            except:
                pass

            if progressbar:
                pbar.update(1)

        if is_new_epoch:
            break

    if progressbar:
        pbar.close()

    # Reset data counters
    dataset.reset()

    if dataset.label_type == 'kanji_wb' or (task_index > 0 and dataset.label_type_sub == 'kanji_wb'):
        wer /= num_words
        sub_word /= num_words
        ins_word /= num_words
        del_word /= num_words
    else:
        wer = sub_word = ins_word = del_word = 0

    cer /= num_chars
    sub_char /= num_chars
    ins_char /= num_chars
    del_char /= num_chars

    df_wer_cer = pd.DataFrame(
        {'SUB': [sub_char * 100, sub_word * 100],
         'INS': [ins_char * 100, ins_word * 100],
         'DEL': [del_char * 100, del_word * 100]},
        columns=['SUB', 'INS', 'DEL'], index=['CER', 'WER'])

    return cer, wer, df_wer_cer
