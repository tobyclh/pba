# Copyright 2018 The TensorFlow Authors All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Helper functions used for training PBA models."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import logging

from autoaugment.helper_utils import cosine_lr  # pylint: disable=unused-import
import torch.optim 


def eval_child_model(session, model, data_loader, mode):
    """Evaluates `model` on held out data depending on `mode`.

  Args:
    session: TensorFlow session the model will be run with.
    model: TensorFlow model that will be evaluated.
    data_loader: DataSet object that contains data that `model` will evaluate.
    mode: Will `model` either evaluate validation or test data.

  Returns:
    Accuracy of `model` when evaluated on the specified dataset.

  Raises:
    ValueError: if invalid dataset `mode` is specified.
  """
    if mode == 'val':
        images = data_loader.val_images
        labels = data_loader.val_labels
    elif mode == 'test':
        images = data_loader.test_images
        labels = data_loader.test_labels
    else:
        raise ValueError('Not valid eval mode')
    assert len(images) == len(labels)
    logging.info('model.batch_size is {}'.format(model.batch_size))
    eval_batches = int(len(images) / model.batch_size)
    if len(images) % model.batch_size != 0:
        eval_batches += 1
    correct = 0
    count = 0
    for i in range(eval_batches):
        eval_images = images[i * model.batch_size:(i + 1) * model.batch_size]
        eval_labels = labels[i * model.batch_size:(i + 1) * model.batch_size]
        preds = session.run(
            model.predictions,
            feed_dict={
                model.images: eval_images,
                model.labels: eval_labels,
            })
        correct += np.sum(
            np.equal(np.argmax(eval_labels, 1), np.argmax(preds, 1)))
        count += len(preds)
    assert count == len(images)
    logging.info('correct: {}, total: {}'.format(correct, count))
    return correct / count

def step_lr(learning_rate, epoch):
  def get_lr(epoch):
    if epoch < 80:
        return learning_rate
    elif epoch < 120:
        return learning_rate * 0.1
    else:
        return learning_rate * 0.01
  return get_lr

def get_lr(curr_epoch, hparams, iteration=None):
    """Returns the learning rate during training based on the current epoch."""
    assert iteration is not None
    batches_per_epoch = int(hparams.train_size / hparams.batch_size)
    if 'svhn' in hparams.dataset and 'wrn' in hparams.model_name:
        lr = step_lr(hparams.lr, curr_epoch)
    elif 'cifar' in hparams.dataset or ('svhn' in hparams.dataset and
                                        'shake_shake' in hparams.model_name):
        lr = cosine_lr(hparams.lr, curr_epoch, iteration, batches_per_epoch,
                       hparams.num_epochs)
    else:
        lr = cosine_lr(hparams.lr, curr_epoch, iteration, batches_per_epoch,
                       hparams.num_epochs)        
        logging.warn('Default to cosine learning rate.')
    return lr


def run_epoch_training(session, model, data_loader, curr_epoch):
    """Runs one epoch of training for the model passed in.

  Args:
    session: TensorFlow session the model will be run with.
    model: TensorFlow model that will be evaluated.
    data_loader: DataSet object that contains data that `model` will evaluate.
    curr_epoch: How many of epochs of training have been done so far.

  Returns:
    The accuracy of 'model' on the training set
  """
    steps_per_epoch = int(model.hparams.train_size / model.hparams.batch_size)
    logging.info('steps per epoch: {}'.format(steps_per_epoch))
    curr_step = session.run(model.global_step)
    assert curr_step % steps_per_epoch == 0

    # Get the current learning rate for the model based on the current epoch
    curr_lr = get_lr(curr_epoch, model.hparams, iteration=0)
    logging.info('lr of {} for epoch {}'.format(curr_lr, curr_epoch))

    correct = 0
    count = 0
    for step in range(steps_per_epoch):
        curr_lr = get_lr(curr_epoch, model.hparams, iteration=(step + 1))
        # Update the lr rate variable to the current LR.
        model.lr_rate_ph.load(curr_lr, session=session)
        if step % 20 == 0:
            logging.info('Training {}/{}'.format(step, steps_per_epoch))

        train_images, train_labels = data_loader.next_batch(curr_epoch)
        _, step, preds = session.run(
            [model.train_op, model.global_step, model.predictions],
            feed_dict={
                model.images: train_images,
                model.labels: train_labels,
            })

        correct += np.sum(
            np.equal(np.argmax(train_labels, 1), np.argmax(preds, 1)))
        count += len(preds)
    train_accuracy = correct / count

    logging.info('Train accuracy: {}'.format(train_accuracy))
    return train_accuracy
