import * as vscode from 'vscode';
import * as path from 'path';

export function activate(context: vscode.ExtensionContext) {

    const scriptPath = path.join(context.extensionPath, 'scripts', 'pyx.py');

    // Helper: VS Codeのタスク機能を使って実行する (コマンドを非表示にするため)
    const runPyxTask = async (extraArgs: string) => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }
        const doc = editor.document;
        if (doc.languageId !== 'pyx') { return; }

        // ファイルを保存
        await doc.save();

        // 設定の読み込み
        const config = vscode.workspace.getConfiguration('pyx');
        const showDisclaimer = config.get<boolean>('showDisclaimer');
        const showOriginal = config.get<boolean>('showOriginalCode');
        const commentStyle = config.get<string>('commentStyle') || "'''";
        const disclaimerText = config.get<string>('disclaimerText') || "";
        
        // Base64エンコード
        const headerB64 = Buffer.from(disclaimerText, 'utf-8').toString('base64');

        // 引数の構築
        let args = extraArgs;
        if (!showDisclaimer) { args += ' --no-header'; }
        if (!showOriginal) { args += ' --no-original'; }
        args += ` --comment-style "${commentStyle}"`;
        args += ` --header-b64 "${headerB64}"`;

        // Pythonコマンドラインの作成
        // python3 "path/to/pyx.py" "path/to/file.pyx" ...args...
        const filePath = doc.fileName;
        const commandLine = `python3 "${scriptPath}" "${filePath}" ${args}`;

        // タスクの定義
        // shell実行として定義することで、python3コマンドを走らせる
        const execution = new vscode.ShellExecution(commandLine);
        
        // タスクの作成
        // TaskScope.Workspace とすることで、現在のワークスペースで実行
        const task = new vscode.Task(
            { type: 'shell' },
            vscode.TaskScope.Workspace,
            'Run', // タスク名
            'Pyx', // ソース名
            execution
        );

        // ★ここが重要：表示オプションの設定
        task.presentationOptions = {
            echo: false,              // コマンド入力を非表示にする！
            reveal: vscode.TaskRevealKind.Always, // 常にターミナルを表示
            focus: true,              // ターミナルにフォーカス
            panel: vscode.TaskPanelKind.Shared,   // ターミナルを共有
            showReuseMessage: false,  // "Terminal will be reused..." を消す
            clear: true               // 実行前に画面をクリアする
        };

        // タスク実行
        try {
            await vscode.tasks.executeTask(task);
        } catch (e) {
            vscode.window.showErrorMessage(`Failed to run Pyx: ${e}`);
        }
    };

    // コマンド1: 実行してクリップボードにコピー (Ctrl+Shift+B)
    let disposableRunAndCopy = vscode.commands.registerCommand('pyx.runAndCopy', () => {
        runPyxTask('--run --copy');
    });

    // コマンド2: 実行のみ (F5)
    let disposableRunOnly = vscode.commands.registerCommand('pyx.runOnly', () => {
        runPyxTask('--run');
    });

    // コマンド3: Pythonファイルとして出力
    let disposableConvert = vscode.commands.registerCommand('pyx.convertToPython', () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { return; }
        
        // 変換だけの場合は output パスが必要なので、上記Taskとは別処理にするか、
        // 単純にここもTask化するかですが、出力パス計算が必要なのでsendTextのままでも良いが
        // 統一感を出すためにTask化します。
        
        const doc = editor.document;
        doc.save().then(async () => {
            const filePath = doc.fileName;
            const outPath = filePath.replace('.pyx', '.py');
            
            const config = vscode.workspace.getConfiguration('pyx');
            const showDisclaimer = config.get<boolean>('showDisclaimer');
            const showOriginal = config.get<boolean>('showOriginalCode');
            const commentStyle = config.get<string>('commentStyle') || "'''";
            const disclaimerText = config.get<string>('disclaimerText') || "";
            const headerB64 = Buffer.from(disclaimerText, 'utf-8').toString('base64');

            let args = `-o "${outPath}"`;
            if (!showDisclaimer) { args += ' --no-header'; }
            if (!showOriginal) { args += ' --no-original'; }
            args += ` --comment-style "${commentStyle}"`;
            args += ` --header-b64 "${headerB64}"`;

            const commandLine = `python3 "${scriptPath}" "${filePath}" ${args}`;
            const execution = new vscode.ShellExecution(commandLine);
            const task = new vscode.Task(
                { type: 'shell' },
                vscode.TaskScope.Workspace,
                'Convert',
                'Pyx',
                execution
            );
            task.presentationOptions = {
                echo: false, // コマンド非表示
                reveal: vscode.TaskRevealKind.Always,
                focus: true,
                clear: true
            };
            
            await vscode.tasks.executeTask(task);
        });
    });

    context.subscriptions.push(disposableRunAndCopy);
    context.subscriptions.push(disposableRunOnly);
    context.subscriptions.push(disposableConvert);
}

export function deactivate() {}