import os
import sys

def patch(fn, s, r):
    try:
        with open(fn, "r") as f:
            c = f.read()
        if s in c:
            with open(fn, "w") as f:
                f.write(c.replace(s, r))
            print(f"SUCESSO: {fn} modificado.")
        else:
            print(f"FALHA: String original não encontrada em {fn}.")
    except Exception as e:
        print(f"ERRO ao processar {fn}: {e}")

def apply_patches():
    print("Aplicando patches para OPL 1907 (Unificação de Listas)...")

    # Disable default APP menu
    patch("src/opl.c", 
          "initSupport(appGetObject(0), APP_MODE, force_reinit);", 
          "// initSupport(appGetObject(0), APP_MODE, force_reinit);")

    # Includes
    patch("src/bdmsupport.c", 
          "#include \"include/bdmsupport.h\"", 
          "#include \"include/bdmsupport.h\"\n#include \"include/appsupport.h\"\n#include \"include/elf-loader.h\"\n#include \"include/util.h\"\n")

    # Variables
    patch("src/bdmsupport.c", 
          "static char bdmDriver[5];", 
          "static char bdmDriver[5];\nstatic int bdmAppCount = 0;\nstatic app_info_t *bdmApps = NULL;\ntypedef struct { int isApp; int originalId; char name[164]; } bdm_unified_item_t;\nstatic bdm_unified_item_t *bdmUnifiedItems = NULL;\nstatic int bdmUnifiedCount = 0;\n")

    # Redirect count
    patch("src/bdmsupport.c", 
          "return bdmGameCount;", 
          "return bdmUnifiedCount;")

    # Redirect structs
    patch("src/bdmsupport.c", 
          "return &bdmGames[id];", 
          "if (bdmUnifiedItems && bdmUnifiedItems[id].isApp) return &bdmApps[bdmUnifiedItems[id].originalId];\n    return &bdmGames[bdmUnifiedItems[id].originalId];")

    patch("src/bdmsupport.c", 
          "return bdmGames[id].name;", 
          "if (bdmUnifiedItems) return bdmUnifiedItems[id].name;\n    return bdmGames[id].name;")

    patch("src/bdmsupport.c", 
          "return bdmGames[id].startup;", 
          "if (bdmUnifiedItems && bdmUnifiedItems[id].isApp) return bdmApps[bdmUnifiedItems[id].originalId].boot;\n    return bdmGames[bdmUnifiedItems[id].originalId].startup;")

    # Helper functions for Apps
    bdm_func = """
static int bdmCompareItems(const void *a, const void *b) { return strcmp(((bdm_unified_item_t*)a)->name, ((bdm_unified_item_t*)b)->name); }

static int bdmScanAppsPath(const char *appsPath, int (*callback)(const char *path, config_set_t *appConfig, void *arg), void *arg) {
    struct dirent *pdirent; DIR *pdir; struct stat st; int count = 0, ret;
    config_set_t *appConfig; char dir[256]; char path[256];
    if ((pdir = opendir(appsPath)) != NULL) {
        while ((pdirent = readdir(pdir)) != NULL) {
            if (pdirent->d_name[0] == '.') continue;
            snprintf(dir, sizeof(dir), "%s%s", appsPath, pdirent->d_name);
            if (stat(dir, &st) < 0 || !S_ISDIR(st.st_mode)) continue;
            snprintf(path, sizeof(path), "%s/title.cfg", dir);
            appConfig = configAlloc(0, NULL, path);
            if (appConfig != NULL) {
                configRead(appConfig);
                ret = callback(dir, appConfig, arg);
                configFree(appConfig);
                if (ret >= 0) count++;
            }
        }
        closedir(pdir);
    }
    return count;
}

static int bdmAppScanCallback(const char *path, config_set_t *appConfig, void *arg) {
    app_info_t *app; const char *title, *boot;
    if (configGetStr(appConfig, "title", &title) && configGetStr(appConfig, "boot", &boot)) {
        bdmApps = realloc(bdmApps, (bdmAppCount + 1) * sizeof(app_info_t));
        app = &bdmApps[bdmAppCount++];
        strncpy(app->title, title, sizeof(app->title));
        strncpy(app->boot, boot, sizeof(app->boot));
        app->title[sizeof(app->title)-1] = '\\0'; app->boot[sizeof(app->boot)-1] = '\\0';
    } return 1;
}
"""
    patch("src/bdmsupport.c", 
          "static void bdmLaunchGame(int id, config_set_t *configSet)", 
          bdm_func + "static void bdmLaunchGame(int id, config_set_t *configSet)")

    # Launch logic
    bdm_launch = """
    if (bdmUnifiedItems && bdmUnifiedItems[id].isApp) {
        app_info_t *app = &bdmApps[bdmUnifiedItems[id].originalId];
        char path[256]; snprintf(path, sizeof(path), "%sAPPS/%s", bdmPrefix, app->boot);
        deinit(NO_EXCEPTION, -1);
        LoadELFFromFileWithPartition(path, "", 0, NULL);
        return;
    }
"""
    patch("src/bdmsupport.c", 
          "static void bdmLaunchGame(int id, config_set_t *configSet)\n{", 
          "static void bdmLaunchGame(int id, config_set_t *configSet)\n{\n" + bdm_launch)

    # Update logic
    bdm_update = """
    if (bdmApps) free(bdmApps); bdmApps = NULL; bdmAppCount = 0;
    char appPath[64]; snprintf(appPath, sizeof(appPath), "%sAPPS/", bdmPrefix);
    bdmScanAppsPath(appPath, bdmAppScanCallback, NULL);
    if (bdmUnifiedItems) free(bdmUnifiedItems); bdmUnifiedItems = NULL; bdmUnifiedCount = 0;
    bdmUnifiedCount = bdmGameCount + bdmAppCount;
    if (bdmUnifiedCount > 0) {
        bdmUnifiedItems = malloc(bdmUnifiedCount * sizeof(bdm_unified_item_t));
        int i, idx = 0;
        for (i=0; i<bdmGameCount; i++, idx++) {
            bdmUnifiedItems[idx].isApp = 0; bdmUnifiedItems[idx].originalId = i;
            strncpy(bdmUnifiedItems[idx].name, bdmGames[i].name, 163);
            bdmUnifiedItems[idx].name[163] = '\\0';
        }
        for (i=0; i<bdmAppCount; i++, idx++) {
            bdmUnifiedItems[idx].isApp = 1; bdmUnifiedItems[idx].originalId = i;
            strncpy(bdmUnifiedItems[idx].name, bdmApps[i].title, 163);
            bdmUnifiedItems[idx].name[163] = '\\0';
        }
        qsort(bdmUnifiedItems, bdmUnifiedCount, sizeof(bdm_unified_item_t), bdmCompareItems);
    }
"""
    patch("src/bdmsupport.c", 
          "static int bdmUpdateGameList(void)\n{\n    sbReadList(&bdmGames, bdmPrefix, &bdmULSizePrev, &bdmGameCount);\n    return bdmGameCount;\n}", 
          "static int bdmUpdateGameList(void)\n{\n    sbReadList(&bdmGames, bdmPrefix, &bdmULSizePrev, &bdmGameCount);\n" + bdm_update + "\n    return bdmUnifiedCount;\n}")

    # Memory cleanup
    patch("src/bdmsupport.c", 
          "free(bdmGames);", 
          "free(bdmGames); bdmGames = NULL;\n        if (bdmApps) { free(bdmApps); bdmApps = NULL; }\n        if (bdmUnifiedItems) { free(bdmUnifiedItems); bdmUnifiedItems = NULL; }")

    print("Patches finalizados!")

if __name__ == "__main__":
    apply_patches()
