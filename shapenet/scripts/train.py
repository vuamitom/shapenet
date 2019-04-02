from ..dataset import DataSet
from ..networks import ShapeNet
import numpy as np
import torch
from tqdm import trange
from tqdm.auto import tqdm
import math

BATCH_SIZE = 1
N_COMPONENTS = 25

def load_pca(pca_path, n_components):
    return np.load(pca_path)['shapes'][:(n_components + 1)]

def load_dataset(path):
    return DataSet(path)

def create_nn(pca):
    net = ShapeNet(pca)
    input_device, output_device = None, None
    # check device
    if torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        if device_count > 1:
            gpu_ids = [i for i in range(0, device_count)]
            input_device = torch.device('cuda:%d' % gpu_ids[0])
            net = torch.nn.DataParallel(net.to(input_device),
                    device_ids=gpu_ids,
                    output_device=gpu_ids[1]
                )
            output_device = torch.device('cuda:%d' % gpu_ids[1])
        else:
            input_device = torch.device('cuda:0')
            net = net.to(input_device)
            output_device = torch.device('cuda:0')        
    else:
        input_device = torch.device('cpu') 
        output_device = torch.device('cpu') 
        net = net.to(input_device)
    return net, input_device, output_device

def create_optimizer(model, lr=0.0001):
    # TODO: read more about mix-precision optimizer https://forums.fast.ai/t/mixed-precision-training/20720
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    return optimizer

def train_single_epoch(model, optimizer, criteria, dataset, input_device, output_device):
    batch_size = BATCH_SIZE
    total_batch = math.ceil(dataset.train_set_size() / batch_size)
    print_every = 100
    total_loss = 0

    for i in trange(0, total_batch):
        data, labels = dataset.next_batch(batch_size)
        data = torch.from_numpy(data).to(input_device).to(torch.float)
        labels = torch.from_numpy(labels).to(output_device).to(torch.float)
        model.train()

        with torch.enable_grad():            
            preds = model(data)
            #cal loss
            loss_vals = {}
            train_loss = 0
            for key, fn in criteria.items():
                _loss_val = fn(preds, labels)
                loss_vals[key] = _loss_val.detach()
                train_loss += _loss_val
                total_loss += _loss_val
            optimizer.zero_grad()
            train_loss.backward()
            optimizer.step()           

        if (i + 1) % print_every == 0:
            tqdm.write('avg. train loss %.2f' % (total_loss / print_every))
            total_loss = 0


def eval(model, val_dataset, criteria, metrics, input_device, output_device):    
    data = torch.from_numpy(val_dataset.data).to(input_device).to(torch.float)
    labels = torch.from_numpy(val_dataset.labels).to(output_device).to(torch.float)
    model.eval()
    with torch.no_grad():
        preds = model(data)
        loss_vals = {}
        total_loss = 0
        for key, fn in criteria.items():
            _loss_val = fn(preds, labels)
            loss_vals[key] = _loss_val.detach()
        for key, metric_fn in metrics.items():
            metric_vals[key] = metric_fn(preds, labels)
    return metric_vals, loss_vals, preds


def train(pca_path, train_data, val_data, num_epochs = 200):    

    n_components = N_COMPONENTS    
    # load PCA
    pca = load_pca(pca_path, n_components)

    # create network 
    net, input_device, output_device = create_nn(pca)

    # load data set
    train_dataset = load_dataset(train_data)
    val_dataset = load_dataset(val_data)

    # define optimizers
    optimizer = create_optimizer(net)
    # loss function
    criteria = {"L1": torch.nn.L1Loss()}

    # load latest epoch if available        
    start_epoch = 0
    # train - just set the mode to 'train'
    net.train()    

    for epoch in range(start_epoch, num_epochs+1):
        # train a single epoch
        train_single_epoch(net, optimizer, criteria, train_dataset, input_device, output_device)

        #validate 
        metric_vals, loss_vals, preds = eval(net, val_dataset, criteria, {}, input_device, output_device)

        print('val loss', loss_vals)
        
def run_train():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--datadir",
                        help="Path to dataset dir",
                        type=str)
    args = parser.parse_args()
    data_dir = args.datadir
    pca_path = os.path.join(data_dir, 'train_pca.npz')
    train_data = os.path.join(data_dir, 'labels_ibug_300W_train.npz')
    val_data = os.path.join(data_dir, 'labels_ibug_300W_test.npz')
    train(pca_path, train_data, val_data)  

if __name__ == '__main__':
    run_train()
