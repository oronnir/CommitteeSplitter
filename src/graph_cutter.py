import json
import random

import numpy as np
import networkx as nx
from collections import Counter


class GraphCutter:
    def __init__(self, graph: nx.Graph):
        self.graph = graph

    def graph_cut_loss(self, partitions: list[set]) -> float:
        """
        Sums the weight of edges in the k-cut of a graph using adjacency matrices.

        Parameters:
        - G (networkx.Graph): The input graph.
        - partitions (list of lists/sets): The k partitions of the graph. Each element is a list or set of nodes forming a partition.

        Returns:
        - float: The sum of the weights of the edges in the k-cut.
        """
        # Create the adjacency matrix of the graph
        weights = nx.to_numpy_array(self.graph)

        # Get the list of all nodes
        all_nodes = list(self.graph.nodes())

        # Iterate over each pair of partitions
        cut_weight = 0
        for i in range(len(partitions)):
            for j in range(i + 1, len(partitions)):
                # Get the indices of the nodes in each partition
                indices_i = [all_nodes.index(node) for node in partitions[i]]
                indices_j = [all_nodes.index(node) for node in partitions[j]]

                # Extract the sub-matrix that corresponds to the edges between the partitions
                cut_matrix = weights[indices_i, :][:, indices_j]

                # Sum the weights of the cut edges between these partitions
                cut_weight += np.sum(cut_matrix)

        return cut_weight

    def _init_cost_node_to_partition(self, num_cuts: int, partitions: list[set], node_to_id_map: dict):
        cost_node_to_partition = np.zeros((len(self.graph.nodes), num_cuts), dtype=int)
        node_to_partition_map = {}
        for p, partition in enumerate(partitions):
            for node in partition:
                node_to_partition_map[node] = p

        for edge in self.graph.edges:
            cost_node_to_partition[node_to_id_map[edge[0]], node_to_partition_map[edge[1]]] += self.graph[edge[0]][edge[1]]['weight']
            cost_node_to_partition[node_to_id_map[edge[1]], node_to_partition_map[edge[0]]] += self.graph[edge[0]][edge[1]]['weight']

        return cost_node_to_partition, node_to_partition_map

    def _init_partition(self, num_cuts: int, init_guess: dict):
        if num_cuts < 2:
            raise ValueError("num_splits must be at least 2")

        if init_guess is not None:
            partitions = [set() for _ in range(num_cuts)]
            for node, group in init_guess.items():
                partitions[group].add(node)
            nodes = sorted(self.graph.nodes, key=lambda n: init_guess[n])
            node_to_id_map = {node: i for i, node in enumerate(nodes)}
            id_to_node_map = {i: node for i, node in enumerate(nodes)}
            return partitions, node_to_id_map, id_to_node_map, nodes

        nodes = sorted(self.graph.nodes, key=lambda n: random.randint(0, 1000))
        # nodes = sorted(self.graph.nodes, key=lambda n: int(n[1:]) if n[1:].isnumeric() else n)
        node_to_id_map = {node: i for i, node in enumerate(nodes)}
        id_to_node_map = {i: node for i, node in enumerate(nodes)}

        # init by randomly assigning nodes to partitions in a balanced way
        partitions = [set() for _ in range(num_cuts)]
        for i, node in enumerate(nodes):
            partitions[i % num_cuts].add(node)

        return partitions, node_to_id_map, id_to_node_map, nodes

    @staticmethod
    def _swap(partitions, from_partition, to_partition, from_swap_ind, to_swap_ind, id_to_node_map):
        partitions[from_partition].remove(id_to_node_map[from_swap_ind])
        partitions[to_partition].add(id_to_node_map[from_swap_ind])
        partitions[to_partition].remove(id_to_node_map[to_swap_ind])
        partitions[from_partition].add(id_to_node_map[to_swap_ind])
        return partitions

    def cut(self, num_cuts, num_iterations, init_guess, convergence_count=500, exploration_prob=0.5) -> list[set]:
        """
        Cut the graph into num_splits partitions while minimizing the cut cost.
        :return: self.num_splits partitions
        """
        print(f'Starting graph cut with {num_cuts} partitions, {num_iterations} iterations and exploration probability of {exploration_prob}.')
        convergence_counter = convergence_count
        init_guess = init_guess if random.random() < 0.5 else None
        partitions, node_to_id_map, id_to_node_map, nodes = self._init_partition(num_cuts, init_guess)

        # iteratively move nodes between partitions to minimize cut cost
        it = 0
        current_cost = np.inf
        past_cost = current_cost
        for it in range(num_iterations):
            cost_node_to_partition, node_to_partition_map = self._init_cost_node_to_partition(num_cuts, partitions, node_to_id_map)

            # pick two random partitions without replacement
            from_partition, to_partition = np.random.choice(num_cuts, 2, replace=False)
            swap_weights = cost_node_to_partition[:, to_partition] - cost_node_to_partition[:, from_partition]

            # mask from partition nodes
            mask_from = np.ones(len(nodes), dtype=bool)
            mask_from[[node_to_id_map[node] for node in partitions[from_partition]]] = False
            masked_swap_from = np.ma.masked_array(swap_weights, mask_from, dtype=int)

            # mask to partition nodes
            mask_to = np.ones(len(nodes), dtype=bool)
            mask_to[[node_to_id_map[node] for node in partitions[to_partition]]] = False
            masked_swap_to = np.ma.masked_array(swap_weights, mask_to, dtype=int)

            # calculate the current cost on crossing the partitions
            current_cost = self.graph_cut_loss(partitions)
            if current_cost < past_cost:
                print(f'\rIteration {it + 1}/{num_iterations}; Total Cut Cost: {current_cost}', end='')
                past_cost = current_cost

            # randomly swap nodes between partitions with probability exploration_prob to minimize the cut
            if np.random.rand() < exploration_prob:
                # randomly swap nodes between partitions
                to_swap_ind = np.random.choice([node_to_id_map[node] for node in partitions[to_partition]])
                from_swap_ind = np.random.choice([node_to_id_map[node] for node in partitions[from_partition]])
            else:
                # find the node with the highest cost to partition and swap it with the node with the highest cost from
                # partition so the cost is minimized and the partitions are kept balanced
                to_swap_ind = np.ma.argmin(masked_swap_to)
                from_swap_ind = np.ma.argmax(masked_swap_from)

            # swap criteria
            gain = swap_weights[from_swap_ind] - swap_weights[to_swap_ind]
            if gain > 0:
                partitions = self._swap(partitions, from_partition, to_partition, from_swap_ind, to_swap_ind, id_to_node_map)
                actual_swap_drop = current_cost - self.graph_cut_loss(partitions)
                if actual_swap_drop <= 0:
                    # undo the swap if the cost is not reduced
                    partitions = self._swap(partitions, from_partition, to_partition, to_swap_ind, from_swap_ind, id_to_node_map)
                else:
                    convergence_counter = convergence_count
            else:
                convergence_counter -= 1
                if convergence_counter == 0:
                    break
        print(f'Converged after {it+1} iterations. Into {num_cuts} partitions.')
        if len(self.graph.nodes) < 10:
            print(f'The cut cost is: {current_cost}')
            print(f'The partitions are: {[p for p in partitions]}')
            print(f'The Cost matrix is:\n{nx.to_numpy_array(self.graph)}')
        return partitions

    def save(self, filepath: str, cuts: list[set], papers: dict):
        """
        Save the graph cut to a file.
        :param filepath: the path the file will be saved to
        :param cuts: the cuts to save
        :param papers: papers to reviewers map
        :return: None
        """
        reviewer_to_room_map = {node: i for i, cut in enumerate(cuts) for node in cut}
        with open(filepath, 'w') as file:
            json.dump(reviewer_to_room_map, file)

        # reviewer to room assignment CSV
        with open(filepath.replace('.json', '_people_rooms.csv'), 'w') as file:
            file.write('Reviewer,Room\n')
            for reviewer, room in reviewer_to_room_map.items():
                file.write(f'{reviewer},{room}\n')

        # paper to room assignment map putting a paper in the room of the most reviewers assigned to
        paper_to_room_map = {paper: Counter([reviewer_to_room_map[r] for r in reviewers_tup]).most_common(1)[0][0] for paper, reviewers_tup in papers.items()}

        # paper to room assignment CSV
        with open(filepath.replace('.json', '_paper_rooms.csv'), 'w') as file:
            file.write('Paper,Room\n')
            for paper, room in paper_to_room_map.items():
                file.write(f'{paper},{room}\n')

    def __str__(self):
        return f"GraphCutter(graph={self.graph})"

    def __repr__(self):
        return str(self)
