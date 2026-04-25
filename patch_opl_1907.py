import os

def patch(fn, s, r):
    try:
        if not os.path.exists(fn): return
        with open(fn, 'r') as f:
            c = f.read()
        if s in c:
            with open(fn, 'w') as f:
                f.write(c.replace(s, r))
            print(f'SUCESSO: {fn} modificado.')
    except Exception as e:
        print(f'ERRO em {fn}: {e}')

def apply_patches():
    print('Aplicando Menu Unificado na Versão 48e2d13...')

    # 1. Desativar o menu de Apps original para evitar duplicidade
    patch('src/opl.c', 'initSupport(appGetObject(0), APP_MODE, force_reinit);', '// initSupport(appGetObject(0), APP_MODE, force_reinit);')

    # 2. Preparar o arquivo bdmsupport.c
    patch('src/bdmsupport.c', '#include "include/bdmsupport.h"', '#include "include/bdmsupport.h"\\n#include "include/appsupport.h"\\n#include "include/elf-loader.h"\\n#include "include/util.h"')
    
    # Injetar estruturas de controle
    vars_unified = """
static int bdmAppCount = 0;
static app_info_t *bdmApps = NULL;
typedef struct { int isApp; int originalId; char name[164]; } bdm_unified_item_t;
static bdm_unified_item_t *bdmUnifiedItems = NULL;
static int bdmUnifiedCount = 0;
"""
    patch('src/bdmsupport.c', 'static int bdmGameCount = 0;', 'static int bdmGameCount = 0;' + vars_unified)

    # Injetar ajudantes (Scan de Apps e Comparação)
    helpers = """
static int bdmCompareItems(const void *a, const void *b) { return strcasecmp(((bdm_unified_item_t*)a)->name, ((bdm_unified_item_t*)b)->name); }
static int bdmAppScanCallback(const char *path, config_set_t *appConfig, void *arg) {
    app_info_t *app; const char *title, *boot;
    if (configGetStr(appConfig, "title", &title) && configGetStr(appConfig, "boot", &boot)) {
        bdmApps = realloc(bdmApps, (bdmAppCount + 1) * sizeof(app_info_t));
        app = &bdmApps[bdmAppCount++];
        strncpy(app->title, title, sizeof(app->title)); strncpy(app->boot, boot, sizeof(app->boot));
        app->title[sizeof(app->title)-1] = '\\0'; app->boot[sizeof(app->boot)-1] = '\\0';
    } return 1;
}
"""
    patch('src/bdmsupport.c', 'static void bdmLaunchGame(int id, config_set_t *configSet)', helpers + 'static void bdmLaunchGame(int id, config_set_t *configSet)')

    # 3. Lógica de Lançamento (Boot)
    boot_logic = """
    if (bdmUnifiedItems && bdmUnifiedItems[id].isApp) {
        app_info_t *app = &bdmApps[bdmUnifiedItems[id].originalId];
        char path[256]; snprintf(path, sizeof(path), "%sAPPS/%s", bdmPrefix, app->boot);
        deinit(NO_EXCEPTION, -1);
        LoadELFFromFileWithPartition(path, "", 0, NULL);
        return;
    }
"""
    patch('src/bdmsupport.c', 'base_game_info_t *game = &bdmGames[id];', boot_logic + '    base_game_info_t *game = &bdmGames[bdmUnifiedItems[id].originalId];')

    # 4. Lógica de Atualização da Lista (Merge)
    merge_logic = """
    if (bdmApps) free(bdmApps); bdmApps = NULL; bdmAppCount = 0;
    char appPath[64]; snprintf(appPath, sizeof(appPath), "%sAPPS/", bdmPrefix);
    extern int oplScanAppsPath(char *path, int (*callback)(const char *path, config_set_t *appConfig, void *arg), void *arg);
    oplScanAppsPath(appPath, &bdmAppScanCallback, NULL);
    if (bdmUnifiedItems) free(bdmUnifiedItems);
    bdmUnifiedCount = bdmGameCount + bdmAppCount;
    if (bdmUnifiedCount > 0) {
        bdmUnifiedItems = malloc(bdmUnifiedCount * sizeof(bdm_unified_item_t));
        int i, idx = 0;
        for (i=0; i<bdmGameCount; i++, idx++) { bdmUnifiedItems[idx].isApp = 0; bdmUnifiedItems[idx].originalId = i; strncpy(bdmUnifiedItems[idx].name, bdmGames[i].name, 163); bdmUnifiedItems[idx].name[163] = '\\0'; }
        for (i=0; i<bdmAppCount; i++, idx++) { bdmUnifiedItems[idx].isApp = 1; bdmUnifiedItems[idx].originalId = i; strncpy(bdmUnifiedItems[idx].name, bdmApps[i].title, 163); bdmUnifiedItems[idx].name[163] = '\\0'; }
        qsort(bdmUnifiedItems, bdmUnifiedCount, sizeof(bdm_unified_item_t), bdmCompareItems);
    }
"""
    patch('src/bdmsupport.c', 'sbReadList(&bdmGames, bdmPrefix, &bdmULSizePrev, &bdmGameCount);', 'sbReadList(&bdmGames, bdmPrefix, &bdmULSizePrev, &bdmGameCount);' + merge_logic)

    # 5. Redirecionar funções da lista para a lista unificada
    patch('src/bdmsupport.c', 'return bdmGameCount;', 'return bdmUnifiedCount;')
    patch('src/bdmsupport.c', 'return (void *)&bdmGames[id];', 'if (bdmUnifiedItems && bdmUnifiedItems[id].isApp) return &bdmApps[bdmUnifiedItems[id].originalId];\\n    return &bdmGames[bdmUnifiedItems[id].originalId];')
    patch('src/bdmsupport.c', 'return bdmGames[id].name;', 'if (bdmUnifiedItems) return bdmUnifiedItems[id].name;\\n    return bdmGames[id].name;')
    patch('src/bdmsupport.c', 'return bdmGames[id].startup;', 'if (bdmUnifiedItems && bdmUnifiedItems[id].isApp) return bdmApps[bdmUnifiedItems[id].originalId].boot;\\n    return bdmGames[bdmUnifiedItems[id].originalId].startup;')
    patch('src/bdmsupport.c', 'return sbPopulateConfig(&bdmGames[id], bdmPrefix, "/");', 'if (bdmUnifiedItems && bdmUnifiedItems[id].isApp) return NULL; // TODO: App Config\\n    return sbPopulateConfig(&bdmGames[bdmUnifiedItems[id].originalId], bdmPrefix, "/");')

    print('Patch para versão 48e2d13 aplicado com sucesso!')

if __name__ == "__main__":
    apply_patches()
