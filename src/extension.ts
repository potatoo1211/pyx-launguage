import * as vscode from 'vscode';
import * as path from 'path';
import * as child_process from 'child_process';

export function activate(context: vscode.ExtensionContext) {

    // 拡張機能内の pyx.py のパスを取得
    const scriptPath = path.join(context.extensionPath, 'scripts', 'pyx.py');

    // コマンド1: 実行してクリップボードにコピー
    let disposableRun = vscode.commands.registerCommand('pyx.runAndCopy', () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }

        const doc = editor.document;
        if (doc.languageId !== 'pyx') { return; } // .pyx以外は無視

        doc.save().then(() => {
            const filePath = doc.fileName;
            
            // ターミナルを作成または取得して実行
            const terminal = vscode.window.activeTerminal || vscode.window.createTerminal("Pyx");
            terminal.show();
            
            // python "path/to/pyx.py" "target.pyx" --run --copy
            // Windows(WSL)パスの扱いを考慮し、単純に文字列で渡す
            terminal.sendText(`python "${scriptPath}" "${filePath}" --run --copy`);
        });
    });

    // コマンド2: Pythonファイルとして出力
    let disposableConvert = vscode.commands.registerCommand('pyx.convertToPython', () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }
        const doc = editor.document;
        
        doc.save().then(() => {
            const filePath = doc.fileName;
            const outPath = filePath.replace('.pyx', '.py');
            
            const terminal = vscode.window.activeTerminal || vscode.window.createTerminal("Pyx");
            terminal.show();
            terminal.sendText(`python "${scriptPath}" "${filePath}" -o "${outPath}"`);
        });
    });

    context.subscriptions.push(disposableRun);
    context.subscriptions.push(disposableConvert);
}

export function deactivate() {}