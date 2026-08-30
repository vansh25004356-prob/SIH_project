const path = require("path");
require("dotenv").config();

const isProduction = process.env.NODE_ENV === "production";
const config = { enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true" };

const makeDevServerV5Compatible = (devServerConfig) => {
  if (!devServerConfig) return devServerConfig;
  const {
    https,
    onAfterSetupMiddleware,
    onBeforeSetupMiddleware,
    onListening,
    setupMiddlewares,
    ...compatibleConfig
  } = devServerConfig;
  compatibleConfig.server = typeof https === "object"
    ? { type: "https", options: https }
    : https ? "https" : "http";
  compatibleConfig.headers = {
    ...compatibleConfig.headers,
    "Cross-Origin-Resource-Policy": "same-origin",
  };
  if (onBeforeSetupMiddleware || setupMiddlewares) {
    compatibleConfig.setupMiddlewares = (middlewares, devServer) => {
      if (onBeforeSetupMiddleware) onBeforeSetupMiddleware(devServer);
      return setupMiddlewares ? setupMiddlewares(middlewares, devServer) : middlewares;
    };
  }
  compatibleConfig.onListening = (devServer) => {
    devServer.close ??= (callback) => devServer.stopCallback(callback);
    if (onListening) onListening(devServer);
    if (onAfterSetupMiddleware) onAfterSetupMiddleware(devServer);
  };
  return compatibleConfig;
};

let setupHealthEndpoints;
let healthPluginInstance;
if (config.enableHealthCheck) {
  const WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

const webpackConfig = {
  // Cleanly disable ESLint-during-build for production instead of relying on the
  // DISABLE_ESLINT_PLUGIN env var, which removes ESLintWebpackPlugin from the base
  // CRA config before craco ever sees it -- craco's own default eslint override then
  // can't find the plugin and logs "Cannot find ESLint plugin (ESLintWebpackPlugin)."
  // Setting `eslint.enable: false` here lets craco remove the plugin itself and log a
  // clean "Disabled ESLint." message instead.
  eslint: { enable: !isProduction },
  webpack: {
    alias: { "@": path.resolve(__dirname, "src") },
    configure: (cfg) => {
      cfg.watchOptions = {
        ...cfg.watchOptions,
        ignored: ["**/node_modules/**", "**/.git/**", "**/build/**", "**/dist/**", "**/coverage/**", "**/public/**"],
      };
      if (config.enableHealthCheck && healthPluginInstance) cfg.plugins.push(healthPluginInstance);
      return cfg;
    },
  },
  babel: {
    loaderOptions: {
      babelrc: false,
      configFile: false,
    },
  },
};

webpackConfig.devServer = (devServerConfig) => makeDevServerV5Compatible(devServerConfig);

if (!isProduction) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    module.exports = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === "MODULE_NOT_FOUND" && err.message.includes("@emergentbase/visual-edits/craco")) {
      console.warn("[visual-edits] visual editing disabled.");
    } else {
      throw err;
    }
  }
} else {
  module.exports = webpackConfig;
}
