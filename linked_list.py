class Node:
    def __init__(self, data):
        self.data = data
        self.next = None

class LinkedList:
    def __init__(self):
        self.head = None

    def insert_at_position(self, position, data):
        if position < 0:
            raise ValueError("Position must be non-negative")
        
        new_node = Node(data)
        
        if position == 0:
            new_node.next = self.head
            self.head = new_node
            return
        
        current = self.head
        for _ in range(position - 1):
            if current is None:
                raise IndexError("Position out of bounds")
            current = current.next
        
        if current is None:
            raise IndexError("Position out of bounds")
        
        new_node.next = current.next
        current.next = new_node

    def print_list(self):
        current = self.head
        while current:
            print(current.data, end=" -> ")
            current = current.next
        print("None")

# Example usage:
if __name__ == "__main__":
    ll = LinkedList()
    ll.insert_at_position(0, 1)
    ll.insert_at_position(1, 2)
    ll.insert_at_position(2, 3)
    ll.print_list()  # Output: 1 -> 2 -> 3 -> None
