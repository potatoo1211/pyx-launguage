import * as vscode from 'vscode';
import * as path from 'path';

export function activate(context: vscode.ExtensionContext) {

    const scriptPath = path.join(context.extensionPath, 'scripts', 'pyx.py');

    // Helper: ターミナルでコマンドを実行する関数
    const runInTerminal = (args: string) => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }
        const doc = editor.document;
        if (doc.languageId !== 'pyx') { return; }

        doc.save().then(() => {
            const filePath = doc.fileName;
            // 既存のPyxターミナルがあれば使い回す、なければ作る
            const terminal = vscode.window.terminals.find(t => t.name === "Pyx") || vscode.window.createTerminal("Pyx");
            terminal.show();
            
            // Windows(WSL)パス対策でパスをクォートで囲む
            terminal.sendText(`python3 "${scriptPath}" "${filePath}" ${args}`);
        });
    };

    // コマンド1: 実行してクリップボードにコピー (Ctrl+Shift+B)
    let disposableRunAndCopy = vscode.commands.registerCommand('pyx.runAndCopy', () => {
        runInTerminal('--run --copy');
    });

    // コマンド2: 実行のみ (F5)
    let disposableRunOnly = vscode.commands.registerCommand('pyx.runOnly', () => {
        runInTerminal('--run');
    });

    // コマンド3: Pythonファイルとして出力
    let disposableConvert = vscode.commands.registerCommand('pyx.convertToPython', () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }
        const doc = editor.document;
        
        doc.save().then(() => {
            const filePath = doc.fileName;
            const outPath = filePath.replace('.pyx', '.py');
            const terminal = vscode.window.terminals.find(t => t.name === "Pyx") || vscode.window.createTerminal("Pyx");
            terminal.show();
            terminal.sendText(`python3 "${scriptPath}" "${filePath}" -o "${outPath}"`);
        });
    });

    context.subscriptions.push(disposableRunAndCopy);
    context.subscriptions.push(disposableRunOnly);
    context.subscriptions.push(disposableConvert);
}

export function deactivate() {}