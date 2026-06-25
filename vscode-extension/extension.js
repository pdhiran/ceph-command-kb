const vscode = require('vscode');
const axios = require('axios');

let statusBarItem;
let diagnosticCollection;

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log('Ceph Command KB extension is now active');

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = "$(database) Ceph KB";
    statusBarItem.tooltip = "Ceph Command Knowledge Base";
    statusBarItem.command = 'ceph-kb.searchCommands';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Create diagnostic collection for inline warnings
    diagnosticCollection = vscode.languages.createDiagnosticCollection('ceph-kb');
    context.subscriptions.push(diagnosticCollection);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('ceph-kb.verifyCommand', verifyCommand)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('ceph-kb.searchCommands', searchCommands)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('ceph-kb.verifyConfig', verifyConfig)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('ceph-kb.reviewScript', reviewScript)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('ceph-kb.insertCommand', insertCommand)
    );

    // Register code actions provider for quick fixes
    context.subscriptions.push(
        vscode.languages.registerCodeActionsProvider(
            ['python', 'shellscript', 'yaml'],
            new CephKBCodeActionProvider(),
            { providedCodeActionKinds: CephKBCodeActionProvider.providedCodeActionKinds }
        )
    );

    // Auto-verify on save if enabled
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(document => {
            const config = vscode.workspace.getConfiguration('ceph-kb');
            if (config.get('autoVerify')) {
                reviewScriptSilent(document);
            }
        })
    );

    // Check API health on activation
    checkApiHealth();
}

async function getApiUrl() {
    const config = vscode.workspace.getConfiguration('ceph-kb');
    return config.get('apiUrl', 'http://localhost:9090');
}

async function checkApiHealth() {
    try {
        const apiUrl = await getApiUrl();
        const response = await axios.get(`${apiUrl}/health`, { timeout: 5000 });
        if (response.data.kb_loaded) {
            statusBarItem.text = `$(database) Ceph KB (${response.data.total_commands} cmds)`;
            statusBarItem.backgroundColor = undefined;
        }
    } catch (error) {
        statusBarItem.text = "$(database) Ceph KB (offline)";
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
        vscode.window.showWarningMessage(
            'Ceph Command KB API is not running. Start it with: python -m ceph_command_kb.server.rest_api'
        );
    }
}

async function verifyCommand() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const selection = editor.selection;
    const text = editor.document.getText(selection);
    
    if (!text) {
        vscode.window.showErrorMessage('No text selected');
        return;
    }

    try {
        const apiUrl = await getApiUrl();
        const response = await axios.post(`${apiUrl}/api/verify_command`, {
            command: text.trim()
        });

        const result = response.data;
        
        if (result.command_verified) {
            vscode.window.showInformationMessage(
                `Command verified: ${result.command} - ${result.description || 'OK'}`
            );
        } else {
            const similar = result.similar_commands ? `\nSimilar: ${result.similar_commands.join(', ')}` : '';
            vscode.window.showWarningMessage(
                `Command not found: ${text}${similar}`
            );
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Error verifying command: ${error.message}`);
    }
}

async function searchCommands() {
    const query = await vscode.window.showInputBox({
        prompt: 'Search Ceph commands',
        placeHolder: 'e.g., nfs cluster, rbd mirror, osd pool'
    });

    if (!query) {
        return;
    }

    try {
        const apiUrl = await getApiUrl();
        const response = await axios.post(`${apiUrl}/api/search_commands`, {
            query: query,
            limit: 20
        });

        const results = response.data.results || [];
        
        if (results.length === 0) {
            vscode.window.showInformationMessage(`No commands found for: ${query}`);
            return;
        }

        const items = results.map(cmd => ({
            label: cmd.name,
            description: cmd.description || '',
            detail: `Binary: ${cmd.binary}`,
            command: cmd.name
        }));

        const selected = await vscode.window.showQuickPick(items, {
            placeHolder: `Found ${results.length} commands`,
            matchOnDescription: true,
            matchOnDetail: true
        });

        if (selected) {
            // Insert the command at cursor
            const editor = vscode.window.activeTextEditor;
            if (editor) {
                editor.edit(editBuilder => {
                    editBuilder.insert(editor.selection.active, selected.command);
                });
            }
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Error searching commands: ${error.message}`);
    }
}

async function verifyConfig() {
    const configName = await vscode.window.showInputBox({
        prompt: 'Enter Ceph config parameter name',
        placeHolder: 'e.g., osd_pool_default_size'
    });

    if (!configName) {
        return;
    }

    try {
        const apiUrl = await getApiUrl();
        const response = await axios.post(`${apiUrl}/api/verify_config`, {
            name: configName
        });

        const result = response.data;
        
        if (result.verified) {
            const info = [
                `Config: ${result.config}`,
                `Type: ${result.type}`,
                `Default: ${result.default}`,
                result.min ? `Min: ${result.min}` : '',
                result.max ? `Max: ${result.max}` : '',
                `Description: ${result.desc || 'N/A'}`
            ].filter(Boolean).join('\n');
            
            vscode.window.showInformationMessage(info, { modal: true });
        } else {
            vscode.window.showWarningMessage(`Config parameter not found: ${configName}`);
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Error verifying config: ${error.message}`);
    }
}

async function reviewScript() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('No active editor');
        return;
    }

    const document = editor.document;
    const text = document.getText();

    try {
        const apiUrl = await getApiUrl();
        const response = await axios.post(`${apiUrl}/api/review_test`, {
            script_content: text
        });

        const result = response.data;
        
        const outputChannel = vscode.window.createOutputChannel('Ceph KB Review');
        outputChannel.clear();
        outputChannel.appendLine('=== Ceph Command KB Script Review ===\n');
        outputChannel.appendLine(`Total commands: ${result.total_commands || 0}`);
        outputChannel.appendLine(`Verified: ${result.verified_commands || 0}`);
        outputChannel.appendLine(`Unverified: ${result.unverified_commands || 0}`);
        outputChannel.appendLine(`Findings: ${result.findings?.length || 0}\n`);

        if (result.findings && result.findings.length > 0) {
            outputChannel.appendLine('Findings:');
            result.findings.forEach((finding, index) => {
                outputChannel.appendLine(`${index + 1}. [${finding.severity}] ${finding.message}`);
                if (finding.line) {
                    outputChannel.appendLine(`   Line: ${finding.line}`);
                }
                if (finding.command) {
                    outputChannel.appendLine(`   Command: ${finding.command}`);
                }
                if (finding.suggested_fix) {
                    outputChannel.appendLine(`   Fix: ${finding.suggested_fix}`);
                }
                outputChannel.appendLine('');
            });
        }

        outputChannel.show();
        
        const findingCount = result.findings?.length || 0;
        if (findingCount > 0) {
            vscode.window.showWarningMessage(
                `Script review: ${findingCount} finding(s). See output for details.`
            );
        } else {
            vscode.window.showInformationMessage('Script review complete: No issues found.');
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Error reviewing script: ${error.message}`);
    }
}

async function reviewScriptSilent(document) {
    try {
        const apiUrl = await getApiUrl();
        const response = await axios.post(`${apiUrl}/api/review_test`, {
            script_content: document.getText()
        });

        const result = response.data;
        const diagnostics = [];

        if (result.findings) {
            result.findings.forEach(finding => {
                if (finding.line) {
                    const line = document.lineAt(finding.line - 1);
                    const range = new vscode.Range(line.range.start, line.range.end);
                    const severity = finding.severity === 'error' 
                        ? vscode.DiagnosticSeverity.Error 
                        : vscode.DiagnosticSeverity.Warning;
                    
                    diagnostics.push(new vscode.Diagnostic(range, finding.message, severity));
                }
            });
        }

        diagnosticCollection.set(document.uri, diagnostics);
    } catch (error) {
        // Silent failure for auto-verify
        console.error('Auto-verify failed:', error.message);
    }
}

async function insertCommand() {
    await searchCommands();
}

class CephKBCodeActionProvider {
    static providedCodeActionKinds = [
        vscode.CodeActionKind.QuickFix
    ];

    provideCodeActions(document, range) {
        const diagnostics = vscode.languages.getDiagnostics(document.uri);
        const actions = [];

        diagnostics.forEach(diagnostic => {
            if (diagnostic.range.intersection(range)) {
                const action = new vscode.CodeAction(
                    'Search for correct Ceph command',
                    vscode.CodeActionKind.QuickFix
                );
                action.command = {
                    command: 'ceph-kb.searchCommands',
                    title: 'Search Ceph Commands'
                };
                actions.push(action);
            }
        });

        return actions;
    }
}

function deactivate() {
    if (diagnosticCollection) {
        diagnosticCollection.dispose();
    }
}

module.exports = {
    activate,
    deactivate
};
