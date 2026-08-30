// craco.config.js
const path = require("path");
require("dotenv").config();

const isProduction = process.env.NODE_ENV === "production";
const isDevServer = !isProduction;

const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

function makeDevServerV5Compatible(devServerConfig) {
  const {
    https,
    onAfterSetupMiddleware,
    onBeforeSetupMiddleware,
    onListening,
    setupMiddlewares,
    ...compatibleConfig
  } = devServerConfig;

  compatibleConfig.server =
    typeof https === "object"
      ? { type: "https", options: https }
      : https
        ? "https"
        : "http";
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
}

let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

const webpackConfig = {
  webpack: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
    configure: (cfg) => {
      cfg.watchOptions = {
        ...cfg.watchOptions,
        ignored: [
          "**/node_modules/**",
          "**/.git/**",
          "**/build/**",
          "**/dist/**",
          "**/coverage/**",
          "**/public/**",
        ],
      };

      if (config.enableHealthCheck && healthPluginInstance) {
        cfg.plugins.push(healthPluginInstance);
      }

      // CRA 5 may inject ESLintWebpackPlugin even when ESLint is configured
      // off. Remove it explicitly for production builds so linting cannot
      // break the production bundle on Render.
      if (isProduction && Array.isArray(cfg.plugins)) {
        cfg.plugins = cfg.plugins.filter((plugin) => {
          const name = plugin && plugin.constructor ? plugin.constructor.name : "";
          return name !== "ESLintWebpackPlugin";
        });
      }

      return cfg;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;
    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }
      setupHealthEndpoints(devServer, healthPluginInstance);
      return middlewares;
    };
  }
  return devServerConfig;
};

if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    module.exports = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === "MODULE_NOT_FOUND" && err.message.includes("@emergentbase/visual-edits/craco")) {
      console.warn("[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled.");
      module.exports = webpackConfig;
    } else {
      throw err;
    }
  }
} else {
  module.exports = webpackConfig;
}

const exportedConfig = module.exports;
const configureDevServer = exportedConfig.devServer;
exportedConfig.devServer = (devServerConfig) =>
  makeDevServerV5Compatible(configureDevServer(devServerConfig));

module.exports = exportedConfig;
