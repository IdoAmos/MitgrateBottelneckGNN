import torch
import torch.nn.functional as F
from torch.nn import BatchNorm1d
from torch.nn import Sequential, Linear, ReLU
from torch_geometric.nn import GINConv, global_add_pool, global_mean_pool


class GIN_CA(torch.nn.Module):

    def __init__(self, dim_features, dim_target, config):
        super(GIN_CA, self).__init__()

        self.config = config
        self.dropout = config['dropout']
        self.embeddings_dim = [config['hidden_units'][0]] + config['hidden_units']
        self.no_layers = len(self.embeddings_dim)
        self.first_h = []
        self.nns = []
        self.convs = []
        self.linears = []
        self.last_layer_fa = config['last_layer_fa']
        if type(self.last_layer_fa) == bool:
            raise ValueError("Using GIN_CA last_layer_fa must be explicit int indicating layer number")
        if self.last_layer_fa >= self.no_layers:
            print('position of wCA layer larger then number of layers, using last layer')
            self.last_layer_fa = self.no_layers - 1

        print('Using wCA layer in layer:', self.last_layer_fa)

        train_eps = config['train_eps']
        if config['aggregation'] == 'sum':
            self.pooling = global_add_pool
        elif config['aggregation'] == 'mean':
            self.pooling = global_mean_pool

        for layer, out_emb_dim in enumerate(self.embeddings_dim):

            if layer == 0:
                self.first_h = Sequential(Linear(dim_features, out_emb_dim), BatchNorm1d(out_emb_dim), ReLU(),
                                          Linear(out_emb_dim, out_emb_dim), BatchNorm1d(out_emb_dim), ReLU())
                self.linears.append(Linear(out_emb_dim, dim_target))
            else:
                input_emb_dim = self.embeddings_dim[layer - 1]
                self.nns.append(Sequential(Linear(input_emb_dim, out_emb_dim), BatchNorm1d(out_emb_dim), ReLU(),
                                           Linear(out_emb_dim, out_emb_dim), BatchNorm1d(out_emb_dim), ReLU()))
                self.convs.append(GINConv(self.nns[-1], train_eps=train_eps))  # Eq. 4.2

                self.linears.append(Linear(out_emb_dim, dim_target))

        self.nns = torch.nn.ModuleList(self.nns) # mpl mapping node features to node features
        self.convs = torch.nn.ModuleList(self.convs) #GIN convs
        self.linears = torch.nn.ModuleList(self.linears)  # has got one more for initial input

    def forward(self, data):
        x, edge_index, batch = data.x, data.edge_index, data.batch

        out = 0

        for layer in range(self.no_layers):
            if layer == 0:
                x = self.first_h(x)

                out += F.dropout(self.pooling(self.linears[layer](x), batch), p=self.dropout)
            else:
                # Layer l ("convolution" layer)
                edges = edge_index
                if layer == self.last_layer_fa or self.last_layer_fa == -1:
                    # 2/2 TODO: changed to modified adj. matric instead FA
                    # block_map = torch.eq(batch.unsqueeze(0), batch.unsqueeze(-1)).int()
                    # edges, _ = torch_geometric.utils.dense_to_sparse(block_map)
                    edges = data.edge_index_mod
                x = self.convs[layer - 1](x, edges)
                out += F.dropout(self.linears[layer](self.pooling(x, batch)), p=self.dropout, training=self.training)

        return out
