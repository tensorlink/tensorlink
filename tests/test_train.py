from src.cryptography.rsa import get_rsa_pub_key
from src.roles.worker import Worker
from src.ml.distributed import DistributedModel
import torch
import json
import copy
import time
from torch.utils.data import DataLoader, TensorDataset
from transformers import BertForSequenceClassification, BertTokenizer, TrainingArguments, Trainer, set_seed
from datasets import Dataset


def prepare_dummy_data(choice):
    texts = ["This is a positive sentence.", "This is a negative sentence."]
    labels = [1, 0]

    # Tokenization
    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
    tokenized_texts = tokenizer(texts, padding=True, truncation=True, return_tensors='pt')

    # dataset
    if choice == 1:
        dataset = TensorDataset(tokenized_texts['input_ids'], tokenized_texts['attention_mask'], torch.tensor(labels))
        dataloader = DataLoader(dataset)
        return dataloader
    elif choice == 2:
        dataset = Dataset.from_dict({
            'input_ids': tokenized_texts['input_ids'].tolist(),
            'attention_mask': tokenized_texts['attention_mask'].tolist(),
            'labels': labels,
        })
        return dataset
    else:
        return tokenized_texts


def simple_train(model, optimizer):
    loss_fn = torch.nn.CrossEntropyLoss()

    dataloader = prepare_dummy_data(1)

    # simple training loop
    for batch in dataloader:
        optimizer.zero_grad()
        input_ids, attention_mask, label = batch
        outputs = model(input_ids, attention_mask=attention_mask, labels=label)
        loss = outputs.loss
        loss.backward()
        optimizer.step()
        print(loss.item())


def d_simple_train(model, optimizer):
    loss_fn = torch.nn.CrossEntropyLoss()

    dataloader = prepare_dummy_data(1)

    # simple training loop
    for batch in dataloader:
        optimizer.zero_grad()
        input_ids, attention_mask, label = batch
        outputs = model(input_ids, attention_mask=attention_mask, labels=label)
        loss = outputs.loss
        model.backward(loss)
        optimizer.step()
        print(loss.item())


def hf_train(model, optimizer):
    optimizer.zero_grad()
    loss_fn = torch.nn.CrossEntropyLoss()

    training_args = TrainingArguments(
        output_dir='../../../Desktop/Projects/tensorlink-lab/tensorlink/tests/results',
        num_train_epochs=1,
        per_device_train_batch_size=1,
        logging_steps=1,
        overwrite_output_dir=True,
    )

    dataset = prepare_dummy_data(2)
    
    def compute_metrics(pred):
        labels = pred.label_ids
        preds = pred.predictions.argmax(-1)
        accuracy = (preds == labels).mean()
        loss = pred.loss
        return {"accuracy": accuracy}
    
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        compute_metrics=compute_metrics
    )

    trainer.train()


def fp_check(model):
    tokenized_texts = prepare_dummy_data(3)
    input_ids = tokenized_texts['input_ids'][0].unsqueeze(0)  # Add batch dimension
    attention_mask = tokenized_texts['attention_mask'][0].unsqueeze(0)  # Add batch dimension

    # Perform a forward pass through the model
    with torch.no_grad():
        outputs = model(input_ids, attention_mask=attention_mask)

    print(outputs.logits)


if __name__ == "__main__":
    ip = "127.0.0.1"
    port = 5026
    set_seed(0)

    # Spawn 3 workers on their own ports + threads
    worker1 = Worker(host=ip, port=port, wallet_address="5HDxH5ntpmr7U3RjEz5g84Rikr93kmtqUWKQum3p3Kdot4Qh",
                     debug=True)
    worker2 = Worker(host=ip, port=port + 1, wallet_address="5HDxH5ntpmr7U3RjEz5g84Rikr93kmtqUWKQum3p3Kdot4Qh",
                     debug=True)
    worker3 = Worker(host=ip, port=port + 2, wallet_address="5HDxH5ntpmr7U3RjEz5g84Rikr93kmtqUWKQum3p3Kdot4Qh",
                     debug=True)

    worker1.master = True  # We must omit this
    worker2.training = True
    # worker3.training = True

    # Open ports and begin the run loop
    worker1.start()
    worker2.start()
    # worker3.start()

    # Hard code workers connecting to the master node, ideally this will be done via smart contract or DHT
    worker1.connect_dht_node(ip, port + 1)

    config = {"encoder": worker1.key_hash}

    # Bert Dummy Run first
    model = BertForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=2)
    # optimizer = torch.optim.Adam(model.parameters(), lr=1e-5)  # Define optimizer here
    time.sleep(15)
    # d_model = DistributedModel(copy.deepcopy(model), worker1, config=config)
    d_model = DistributedModel(copy.deepcopy(model), worker1)

    d_optimizer = torch.optim.Adam(d_model.parameters(), lr=1e-5)

    param_change = not torch.allclose(list(model.parameters())[0], list(d_model.model.parameters())[0])
    print("WEIGHT UPDATE CHECK:", param_change)

    # test this:
    # torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0) # not sure if this would work with distributed    

    # fp_check(model)
    # simple_train(model, optimizer)
    # hf_train(model, optimizer)

    # Distributed Model Bert Run
    fp_check(d_model)
    d_simple_train(d_model, d_optimizer)
    param_change = not torch.allclose(list(model.parameters())[0], list(d_model.model.parameters())[0])
    print('*'*100)
    print("WEIGHT UPDATE CHECK:", param_change)
    # hf_train(d_model, d_optimizer)

    # with open("distributed_graph.json", "w") as f:
    #     json.dump(graph, f, indent=4)

    # training loop 

    worker1.stop()
    worker2.stop()
    worker3.stop()
