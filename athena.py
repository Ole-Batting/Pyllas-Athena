import sys
import faulthandler

import chess
import chess.pgn
import chess.svg
from PyQt5 import QtCore
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from stockfish import Stockfish

BORDER = 10
PAD = 20
BOARDSIZE = 540
LINESWIDTH = 540
WIDTH = 2 * BORDER + BOARDSIZE + LINESWIDTH + PAD
HEIGHT = 2 * BORDER + BOARDSIZE
LINESX = BORDER + BOARDSIZE + PAD
NODEW = 60
NODEH = 30


# def trace(frame, event, arg):
#     print("%s, %s:%d" % (event, frame.f_code.co_filename, frame.f_lineno))
#     return trace


# sys.settrace(trace)
faulthandler.enable()


class MyWidget(QWidget):
    keyPressed = QtCore.pyqtSignal(int)
    updateDisplay = QtCore.pyqtSignal()
    
    def __init__(self, app):
        super().__init__()
        self.app = app

        self.setGeometry(0, 0, WIDTH, HEIGHT)
        self.board_widget = QSvgWidget(parent=self)
        self.board_widget.setGeometry(BORDER, BORDER, BOARDSIZE, BOARDSIZE)
        self.sheet_widgets: list[QLabel] = list()
        self.lines_widgets: list[list[dict[chess.Color, QLabel]]] = list()
        self.node_widgets: dict[chess.pgn.GameNode, QLabel] = dict()
        self.node_variation: dict[chess.pgn.GameNode, int] = dict()
        self.build_sheet()

        self.game = None
        self.node = None
        self.stockfish_depth = 30
        self.stockfish_threads = 1
        self.stockfish = Stockfish(
            depth=self.stockfish_depth,
            parameters=dict(Threads=self.stockfish_threads)
        )

        self.threadpool = QtCore.QThreadPool()
        self.keyPressed.connect(self.on_key)
        self.updateDisplay.connect(self.display_main)

        self.n_vars = 0

    def keyPressEvent(self, event):
        super(MyWidget, self).keyPressEvent(event)
        self.keyPressed.emit(event.key())
    
    def load_pgn(self, path):
        with open(path) as pgn_file:
            self.game = chess.pgn.read_game(pgn_file)
        self.node = self.game
        self.updateDisplay.emit()
    
    def get_board(self, node=None):
        if node is None:
            node = self.node
        return node.board()
    
    def get_fen(self, node=None):
        return self.get_board(node).fen()
    
    def build_sheet(self, lines: int = 18, vars: int = 4):
        self.lines_widgets = list()
        colors = [181818,212121]
        x = LINESX
        for i in range(lines):
            y = i * NODEH + BORDER
            row = QLabel(parent=self)
            row.setGeometry(x, y, LINESWIDTH, NODEH)
            row.setStyleSheet(f"background-color: #{colors[i % 2]}")
            self.sheet_widgets.append(row)
            self.lines_widgets.append(list())
            for j in range(vars):
                x1 = x + j * (2 * NODEW + PAD)
                white = QLabel(parent=self)
                white.setGeometry(x1, y, NODEW, NODEH)
                white.setIndent(BORDER)
                x2 = x1 + NODEW
                black = QLabel(parent=self)
                black.setGeometry(x2, y, NODEW, NODEH)
                black.setIndent(BORDER)
                self.lines_widgets[-1].append({chess.WHITE: white, chess.BLACK: black})
    
    def _build_lines(self, node: chess.pgn.GameNode):
        if node not in self.node_widgets and node.move is not None:
            row = (node.ply() - 1) // 2
            text = node.parent.board().san(node.move)
            
            if node.is_mainline():
                var = 0
            elif node in self.node_variation:
                var = self.node_variation[node]
            else:
                raise Exception(f"missing var for {node}")
            node_widget = self.lines_widgets[row][var][node.parent.turn()]
            node_widget.setText(text)
            self.node_widgets[node] = node_widget

        if node in self.node_widgets:
            self.node_widgets[node].setStyleSheet("") 

        for child_node in node.variations:
            if not child_node.starts_variation():
                self._build_lines(child_node)
            else:
                self._build_lines(child_node)
    
    def build_lines(self):
        self._build_lines(self.game)
    
    def display_main(self):
        board = self.get_board()
        self.chessboardSvg = chess.svg.board(board).encode("UTF-8")
        self.board_widget.load(self.chessboardSvg)
        self.build_lines()
        if self.node in self.node_widgets:
            self.node_widgets[self.node].setStyleSheet("background-color: gray")
        self.show()
    
    def next_in_line(self):
        next_node = self.node.next()
        if next_node is not None:
            self.node = next_node
        else:
            print("end of line")
    
    def previous_in_line(self):
        previous_node = self.node.parent
        if previous_node is not None:
            self.node = previous_node
        else:
            print("start of line")
    
    def next_variation(self):
        if len(self.node.parent.variations) > 1:
            parent = self.node.parent
            index = None
            for i, o in enumerate(parent.variations):
                if o == self.node:
                    index = i
                    break
            if index is not None and (index + 1) < len(parent.variations):
                self.node = parent.variations[index + 1]
    
    def previous_variation(self):
        if len(self.node.parent.variations) > 1:
            parent = self.node.parent
            index = None
            for i, o in enumerate(parent.variations):
                if o == self.node:
                    index = i
                    break
            if index is not None and (index - 1) >= 0:
                self.node = parent.variations[index - 1]
    
    def move(
            self,
            move: chess.Move,
            node: chess.pgn.GameNode = None,
            is_var: bool = False,
    ) -> chess.pgn.GameNode:
        if node is None:
            node = self.node
        if is_var:
            node.add_variation(move)
            next_node = node.variation(move)
            self.n_vars += 1
            var = self.n_vars
            self.node_variation[next_node] = var
        else:
            node.add_line([move])
            next_node = node.next()
            var = self.node_variation[node]
            self.node_variation[next_node] = var
        return next_node
        
    def get_best_move(self, node=None, stockfish=None) -> chess.Move:
        if stockfish is None:
            stockfish = self.stockfish
        stockfish.set_fen_position(self.get_fen(node))
        return chess.Move.from_uci(stockfish.get_best_move())

    def mainline_variation(self, depth=2):
        stockfish = Stockfish(
            depth=self.stockfish_depth,
            parameters=dict(Threads=self.stockfish_threads)
        )
        node = self.node
        while node.next() is not None:
            move = self.get_best_move(node, stockfish)
            if node.next().move == move:
                node = node.next()
            else:
                break
        node = self.move(move, node, node.next() is not None)
        self.updateDisplay.emit()

        for i in range(depth * 2 - 1):
            move = self.get_best_move(node, stockfish)
            node = self.move(move, node, False)
            self.updateDisplay.emit()
    
    def eval(self):
        self.stockfish.set_fen_position(self.get_fen())
        print(self.stockfish.get_wdl_stats())
        print(self.stockfish.get_evaluation())

    def on_key(self, key):
        # test for a specific key
        if key == QtCore.Qt.Key_Down:
            self.next_in_line()
        elif key == QtCore.Qt.Key_Up:
            self.previous_in_line()
        elif key == QtCore.Qt.Key_Right:
            self.next_variation()
        elif key == QtCore.Qt.Key_Left:
            self.previous_variation()
        elif key == QtCore.Qt.Key_Escape:
            app.exit(0)
        elif key == QtCore.Qt.Key_Return:
            worker = Worker(func=self.mainline_variation, depth=10)
            self.threadpool.start(worker)
        elif key == QtCore.Qt.Key_P:
            print(self.game)
        elif key == QtCore.Qt.Key_E:
            self.eval()
        else:
            print('key pressed: %i' % key)
        
        self.updateDisplay.emit()


class Worker(QtCore.QRunnable):
    def __init__(self, func, **kwargs):
        super(Worker, self).__init__()
        self.func = func
        self.kwargs = kwargs

    @QtCore.pyqtSlot()
    def run(self):
        self.func(**self.kwargs)
    

if __name__ == "__main__":
    app = QApplication([])
    window = MyWidget(app)
    window.load_pgn("IveBeenCalledWorse_vs_NotNotHaze_2023.11.03.pgn")
    app.exec()

# board = chess.Board()
# stockfish = Stockfish(depth=15, parameters=dict(Threads=2))
# with open("IveBeenCalledWorse_vs_NotNotHaze_2023.11.03.pgn") as pgn_file:
#     game = chess.pgn.read_game(pgn_file)

# for move in game.mainline_moves():
#     print(board.san(move))

#     top = stockfish.get_top_moves(1)
#     print(chess.svg.board(game.board()))

#     board.push(move)
#     stockfish.make_moves_from_current_position([move])
